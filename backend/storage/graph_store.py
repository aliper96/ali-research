"""
Memgraph knowledge graph store for ali_researcher.

Stores papers as nodes and citation/relation edges, then runs
MAGE graph algorithms (PageRank, community detection, betweenness
centrality) to compute richer graph metrics for the frontend.
"""
from __future__ import annotations

import logging
import os
from typing import Any

try:
    from neo4j import GraphDatabase, Driver
    _NEO4J_AVAILABLE = True
except ImportError:
    GraphDatabase = None  # type: ignore
    Driver = None  # type: ignore
    _NEO4J_AVAILABLE = False

logger = logging.getLogger(__name__)

_MEMGRAPH_URI = os.environ.get("MEMGRAPH_URI", "bolt://localhost:7687")
_MEMGRAPH_USER = os.environ.get("MEMGRAPH_USER", "")
_MEMGRAPH_PASS = os.environ.get("MEMGRAPH_PASS", "")


class GraphStore:
    """Thin wrapper around the Memgraph bolt driver."""

    def __init__(self) -> None:
        self._driver: Driver | None = None

    def _get_driver(self) -> "Driver | None":
        if not _NEO4J_AVAILABLE:
            return None
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                _MEMGRAPH_URI,
                auth=(_MEMGRAPH_USER, _MEMGRAPH_PASS) if _MEMGRAPH_USER else ("", ""),
            )
        return self._driver

    def _run(self, query: str, params: dict | None = None) -> list[dict]:
        try:
            driver = self._get_driver()
            if driver is None:
                return []
            with driver.session() as session:
                result = session.run(query, params or {})
                return [dict(record) for record in result]
        except Exception as exc:
            logger.error("Memgraph query failed: %s | query: %.120s", exc, query)
            return []

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def upsert_paper(self, paper: dict, session_id: str) -> None:
        """Create or update a Paper node."""
        self._run(
            """
            MERGE (p:Paper {id: $id})
            SET p.title          = $title,
                p.year           = $year,
                p.citation_count = $citation_count,
                p.relevance_score= $relevance_score,
                p.abstract       = $abstract,
                p.url            = $url,
                p.arxiv_id       = $arxiv_id,
                p.session_id     = $session_id
            WITH p
            UNWIND $tags AS tag
            MERGE (t:Tag {name: tag})
            MERGE (p)-[:HAS_TAG]->(t)
            """,
            {
                "id": paper.get("id", ""),
                "title": paper.get("title", ""),
                "year": paper.get("year") or 0,
                "citation_count": paper.get("citation_count", 0),
                "relevance_score": paper.get("relevance_score", 0.0),
                "abstract": (paper.get("abstract") or "")[:500],
                "url": paper.get("url", ""),
                "arxiv_id": paper.get("arxiv_id") or "",
                "session_id": session_id,
                "tags": paper.get("tags", []),
            },
        )

    def upsert_citation(self, source_id: str, target_id: str) -> None:
        """Create a CITES edge between two Paper nodes."""
        self._run(
            """
            MATCH (a:Paper {id: $src}), (b:Paper {id: $tgt})
            MERGE (a)-[:CITES]->(b)
            """,
            {"src": source_id, "tgt": target_id},
        )

    def upsert_related(self, id_a: str, id_b: str, score: float = 0.5) -> None:
        """Create a RELATED_TO edge (undirected, stored as directed both ways)."""
        self._run(
            """
            MATCH (a:Paper {id: $a}), (b:Paper {id: $b})
            MERGE (a)-[r:RELATED_TO]->(b) SET r.score = $score
            MERGE (b)-[r2:RELATED_TO]->(a) SET r2.score = $score
            """,
            {"a": id_a, "b": id_b, "score": score},
        )

    # ------------------------------------------------------------------
    # Graph algorithms (MAGE)
    # ------------------------------------------------------------------

    def run_pagerank(self, session_id: str) -> dict[str, float]:
        """Run PageRank on Paper nodes for this session and return id→score map."""
        rows = self._run(
            """
            CALL pagerank.get()
            YIELD node, rank
            WHERE node:Paper AND node.session_id = $sid
            RETURN node.id AS id, rank
            """,
            {"sid": session_id},
        )
        return {r["id"]: r["rank"] for r in rows}

    def run_community_detection(self, session_id: str) -> dict[str, int]:
        """Run Louvain community detection, return id→community_id map."""
        rows = self._run(
            """
            CALL community_detection.get()
            YIELD node, community_id
            WHERE node:Paper AND node.session_id = $sid
            RETURN node.id AS id, community_id
            """,
            {"sid": session_id},
        )
        return {r["id"]: r["community_id"] for r in rows}

    def run_betweenness(self, session_id: str) -> dict[str, float]:
        """Run betweenness centrality, return id→score map."""
        rows = self._run(
            """
            CALL betweenness_centrality.get()
            YIELD node, betweenness_centrality
            WHERE node:Paper AND node.session_id = $sid
            RETURN node.id AS id, betweenness_centrality AS bc
            """,
            {"sid": session_id},
        )
        return {r["id"]: r["bc"] for r in rows}

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_graph_data(self, session_id: str) -> dict[str, Any]:
        """
        Return enriched graph data for the frontend:
        nodes with pagerank/community/betweenness, edges with type.
        """
        # Run algorithms — gracefully fall back to empty dicts on failure
        pagerank = self.run_pagerank(session_id)
        communities = self.run_community_detection(session_id)
        betweenness = self.run_betweenness(session_id)

        # Fetch all paper nodes for this session
        nodes_raw = self._run(
            """
            MATCH (p:Paper {session_id: $sid})
            RETURN p.id AS id, p.title AS title, p.year AS year,
                   p.citation_count AS citation_count,
                   p.relevance_score AS relevance_score,
                   p.url AS url, p.arxiv_id AS arxiv_id
            """,
            {"sid": session_id},
        )

        # Fetch all edges between papers in this session
        edges_raw = self._run(
            """
            MATCH (a:Paper {session_id: $sid})-[r]->(b:Paper {session_id: $sid})
            RETURN a.id AS source, b.id AS target, type(r) AS rel_type
            """,
            {"sid": session_id},
        )

        # Normalise pagerank 0-1 for node sizing
        pr_values = list(pagerank.values()) or [0.0]
        pr_max = max(pr_values) or 1.0
        pr_min = min(pr_values)

        def _norm_pr(pr: float) -> float:
            if pr_max == pr_min:
                return 0.5
            return (pr - pr_min) / (pr_max - pr_min)

        nodes = [
            {
                "id": r["id"],
                "title": r["title"],
                "year": r["year"],
                "citation_count": r["citation_count"],
                "relevance_score": r["relevance_score"],
                "url": r["url"],
                "arxiv_id": r["arxiv_id"],
                # Graph metrics
                "pagerank": pagerank.get(r["id"], 0.0),
                "pagerank_norm": _norm_pr(pagerank.get(r["id"], 0.0)),
                "community_id": communities.get(r["id"], 0),
                "betweenness": betweenness.get(r["id"], 0.0),
            }
            for r in nodes_raw
        ]

        edges = [
            {
                "source": r["source"],
                "target": r["target"],
                "type": r["rel_type"],
            }
            for r in edges_raw
        ]

        return {
            "nodes": nodes,
            "edges": edges,
            "communities": len(set(communities.values())) if communities else 0,
        }

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def clear_session(self, session_id: str) -> None:
        """Remove all Paper nodes (and their edges) for a session."""
        self._run(
            "MATCH (p:Paper {session_id: $sid}) DETACH DELETE p",
            {"sid": session_id},
        )

    # ------------------------------------------------------------------
    # Global graph (accumulates across all sessions)
    # ------------------------------------------------------------------

    def upsert_global_paper(self, paper: dict) -> None:
        """Create or update a GlobalPaper node (shared across sessions)."""
        self._run(
            """
            MERGE (p:GlobalPaper {id: $id})
            ON CREATE SET p.first_seen = timestamp()
            SET p.title          = $title,
                p.year           = $year,
                p.citation_count = $citation_count,
                p.relevance_score= CASE
                    WHEN p.relevance_score IS NULL THEN $relevance_score
                    ELSE (p.relevance_score + $relevance_score) / 2.0
                END,
                p.url            = $url,
                p.arxiv_id       = $arxiv_id,
                p.session_count  = COALESCE(p.session_count, 0) + 1,
                p.last_seen      = timestamp()
            WITH p
            UNWIND $tags AS tag
            MERGE (t:Tag {name: tag})
            MERGE (p)-[:HAS_TAG]->(t)
            """,
            {
                "id": paper.get("id", ""),
                "title": paper.get("title", ""),
                "year": paper.get("year") or 0,
                "citation_count": paper.get("citation_count", 0),
                "relevance_score": paper.get("relevance_score", 0.0),
                "url": paper.get("url", ""),
                "arxiv_id": paper.get("arxiv_id") or "",
                "tags": paper.get("tags", []),
            },
        )

    def upsert_global_citation(self, source_id: str, target_id: str) -> None:
        """Create a CITES edge between two GlobalPaper nodes."""
        self._run(
            """
            MATCH (a:GlobalPaper {id: $src}), (b:GlobalPaper {id: $tgt})
            MERGE (a)-[:CITES]->(b)
            """,
            {"src": source_id, "tgt": target_id},
        )

    def upsert_global_related(self, id_a: str, id_b: str, score: float = 0.5) -> None:
        """Create a RELATED_TO edge between two GlobalPaper nodes."""
        self._run(
            """
            MATCH (a:GlobalPaper {id: $a}), (b:GlobalPaper {id: $b})
            MERGE (a)-[r:RELATED_TO]->(b) SET r.score = $score
            MERGE (b)-[r2:RELATED_TO]->(a) SET r2.score = $score
            """,
            {"a": id_a, "b": id_b, "score": score},
        )

    def get_global_graph_data(self) -> dict[str, Any]:
        """
        Return enriched global graph data (all sessions merged):
        nodes with pagerank/community/betweenness, edges with type.
        """
        # Run algorithms on GlobalPaper subgraph
        pagerank_rows = self._run(
            """
            CALL pagerank.get()
            YIELD node, rank
            WHERE node:GlobalPaper
            RETURN node.id AS id, rank
            """
        )
        pagerank = {r["id"]: r["rank"] for r in pagerank_rows}

        community_rows = self._run(
            """
            CALL community_detection.get()
            YIELD node, community_id
            WHERE node:GlobalPaper
            RETURN node.id AS id, community_id
            """
        )
        communities = {r["id"]: r["community_id"] for r in community_rows}

        betweenness_rows = self._run(
            """
            CALL betweenness_centrality.get()
            YIELD node, betweenness_centrality
            WHERE node:GlobalPaper
            RETURN node.id AS id, betweenness_centrality AS bc
            """
        )
        betweenness = {r["id"]: r["bc"] for r in betweenness_rows}

        nodes_raw = self._run(
            """
            MATCH (p:GlobalPaper)
            RETURN p.id AS id, p.title AS title, p.year AS year,
                   p.citation_count AS citation_count,
                   p.relevance_score AS relevance_score,
                   p.url AS url, p.arxiv_id AS arxiv_id,
                   p.session_count AS session_count
            """
        )

        edges_raw = self._run(
            """
            MATCH (a:GlobalPaper)-[r]->(b:GlobalPaper)
            RETURN a.id AS source, b.id AS target, type(r) AS rel_type
            """
        )

        pr_values = list(pagerank.values()) or [0.0]
        pr_max = max(pr_values) or 1.0
        pr_min = min(pr_values)

        def _norm_pr(pr: float) -> float:
            if pr_max == pr_min:
                return 0.5
            return (pr - pr_min) / (pr_max - pr_min)

        nodes = [
            {
                "id": r["id"],
                "title": r["title"],
                "year": r["year"],
                "citation_count": r["citation_count"],
                "relevance_score": r["relevance_score"],
                "url": r["url"],
                "arxiv_id": r["arxiv_id"],
                "session_count": r.get("session_count", 1),
                "pagerank": pagerank.get(r["id"], 0.0),
                "pagerank_norm": _norm_pr(pagerank.get(r["id"], 0.0)),
                "community_id": communities.get(r["id"], 0),
                "betweenness": betweenness.get(r["id"], 0.0),
            }
            for r in nodes_raw
        ]

        edges = [
            {"source": r["source"], "target": r["target"], "type": r["rel_type"]}
            for r in edges_raw
        ]

        return {
            "nodes": nodes,
            "edges": edges,
            "communities": len(set(communities.values())) if communities else 0,
            "total_papers": len(nodes),
        }

    def is_available(self) -> bool:
        """Return True if neo4j driver is installed and Memgraph is reachable."""
        if not _NEO4J_AVAILABLE:
            return False
        try:
            result = self._run("RETURN 1")
            return len(result) > 0
        except Exception:
            return False


graph_store = GraphStore()
