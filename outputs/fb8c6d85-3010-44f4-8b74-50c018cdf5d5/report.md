# Research Report

## Summary

“Image to 3D world” is a broad topic covering methods that transform one or a few images into a 3D scene representation suitable for novel-view rendering. The core modern approaches fall into (i) NeRF-based pipelines that reconstruct a continuous radiance field and (ii) 3D Gaussian Splatting (3DGS) pipelines that represent scenes as sets of Gaussians optimized for fast rendering. In practice, single-image methods (and sparse-view methods) face fundamental ambiguity: multiple 3D configurations can explain the same 2D image. As a result, recent work increasingly uses strong generative priors (diffusion/video diffusion) or learned feed-forward networks to hallucinate or regularize missing 3D information.

From the papers gathered so far, a clear theme is leveraging diffusion-based or generative mechanisms to mitigate under-constrained reconstruction. For example, “Generative Lifting of Multiview to 3D from Unknown Pose: Wrapping NeRF inside Diffusion” learns both pose and a NeRF by wrapping them in a diffusion/denoising objective. “Deceptive-NeRF/3DGS” densifies sparse-view inputs by generating diffusion-based pseudo-observations (pseudo images) and then training NeRF/3DGS as if those views were real. For more direct single-view reconstruction, Google Scholar results indicate transformer/gaussian hybrids (e.g., “Triplane meets gaussian splatting”) aiming at generalizable fast single-view reconstruction. Finally, the topic also intersects with 3D generation/editing and completion: “Inpaint3D” and related works distill 2D diffusion priors into NeRF to fill masked regions, while “Text2NeRF” shows how text-driven generation can be used to create 3D scenes using NeRF updates guided by depth and inpainting strategies.

## Key Concepts

`Neural Radiance Fields (NeRF)`  `3D Gaussian Splatting (3DGS)`  `Single-view to 3D reconstruction`  `Diffusion models as priors and training objectives`  `Pseudo-observations / view densification`  `Score distillation / NeRF optimization from diffusion`  `View consistency and occlusion handling`  `Text/image-to-3D scene generation (adjacent paradigm)`

## Papers

### [Generative Lifting of Multiview to 3D from Unknown Pose: Wrapping NeRF inside Diffusion](https://www.semanticscholar.org/paper/ad0c4fbafafb7f2fe94cc3720113077be2f17c3e)

**Xin Yuan, Rana Hanocka, Michael Maire** (2024) · relevance 93%

> We cast multiview reconstruction from unknown pose as a generative modeling problem. From a collection of unannotated 2D images of a scene, our approach simultaneously learns both a network to predict camera pose from 2D image input, as well as the parameters of a Neural Radiance Field (NeRF) for th…

*Why relevant:* Directly targets the “image(s) -> 3D scene” setting but with unknown camera pose; uses diffusion as a training objective to jointly learn pose and NeRF, addressing core ambiguity in image-to-3D lifting.

### [Deceptive-NeRF/3DGS: Diffusion-Generated Pseudo-observations for High-Quality Sparse-View Reconstruction](https://www.semanticscholar.org/paper/d7cffb13dc787cd5bca894a65bb3815dae2d5e74)

**Xinhang Liu, Shiu-hong Kao, Jiaben Chen** (2023) · relevance 88%

> Novel view synthesis via NeRFs or 3D Gaussian Splatting (3DGS) typically necessitates dense observations with hundreds of input images to circumvent artifacts. We introduce Deceptive-NeRF/3DGS to enhance sparse-view reconstruction with only a limited set of input images, by leveraging a diffusion mo…

*Why relevant:* A strong example of the “image-to-3D” line for sparse inputs, using diffusion-generated pseudo views to reconstruct NeRF/3DGS with fewer images (closely related to single-image constraints).

### [Inpaint3D: 3D Scene Content Generation using 2D Inpainting Diffusion](https://www.semanticscholar.org/paper/071c61e03737de1297c07d6bae6aa9c8a2a669c7)

**Kira Prabhu, Jane Wu, Lynn Tsai** (2023) · relevance 82%

> This paper presents a novel approach to inpainting 3D regions of a scene, given masked multi-view images, by distilling a 2D diffusion model into a learned 3D scene representation (e.g. a NeRF). Unlike 3D generative methods that explicitly condition the diffusion model on camera pose or multi-view i…

*Why relevant:* Shows how a single 2D diffusion prior can be used to generate/complete 3D content via NeRF optimization—relevant to image-to-3D world completion and unobserved regions.

### [Text2NeRF: Text-Driven 3D Scene Generation With Neural Radiance Fields](https://www.semanticscholar.org/paper/213a14d426acebf2f04709eea722a887a1f5f051)

**Jingbo Zhang, Xiaoyu Li, Ziyu Wan** (2023) · relevance 74%

> Text-driven 3D scene generation is widely applicable to video gaming, film industry, and metaverse applications that have a large demand for 3D scenes. However, existing text-to-3D generation methods are limited to producing 3D objects with simple geometries and dreamlike styles that lack realism. I…

*Why relevant:* Not image-only (text-driven), but it is directly in the “produce a navigable 3D scene” direction using NeRF + diffusion guidance and view-consistency via inpainting/updating—conceptually adjacent to image-to-3D world generation.

### [Triplane meets gaussian splatting: Fast and generalizable single-view 3D reconstruction with transformers](http://openaccess.thecvf.com/content/CVPR2024/html/Zou_Triplane_Meets_Gaussian_Splatting_Fast_and_Generalizable_Single-View_3D_Reconstruction_CVPR_2024_paper.html)

**ZX Zou, Z Yu, YC Guo** (2024) · relevance 70%

> We propose a method that enables fast reconstruction from a single-view image. We build the 3D representation upon a hybrid Triplane-Gaussian representation by evaluating a ...…

*Why relevant:* Single-view image-to-3D reconstruction using a transformer and a Gaussian splatting-based representation; highly relevant to the single-image setting implied by “image to 3D world.”

### [3D Scene Generation: A Survey](https://www.semanticscholar.org/paper/35b94ed29ed0e4627be9799e01873e91b1bba34f)

**Beichen Wen, Haozhe Xie, Zhaoxi Chen** (2025) · relevance 63%

> 3D scene generation seeks to synthesize spatially structured, semantically meaningful, and photorealistic environments. This survey provides an overview of state-of-the-art approaches, organizing them into four paradigms: procedural generation, neural 3D-based generation, image-based generation, and…

*Why relevant:* Survey-level coverage to contextualize image-to-3D world approaches (NeRF/3DGS, diffusion/video/implicit 3D generation paradigms) and to identify evaluation and challenge areas.

## Research Gaps

- No full-text methods/results extracted for the key single-view reconstruction papers found via Google Scholar (e.g., Triplane+Gaussian Splatting). This prevents precise comparison of training losses, datasets, and failure modes.
- The gathered set focuses more on sparse-view and diffusion-guided lifting/completion than on strictly “image-only” (monocular) generation of a full navigable 3D world; additional targeted single-view reconstruction papers (NeRF- or 3DGS-based) are needed.
- Evaluation coverage is limited: we have not yet compiled benchmark protocols or metrics specifically for image-to-3D/world tasks (geometry, semantic correctness, and view-consistency under occlusion).

## Implementation Roadmap

### Choose representation target (NeRF vs 3DGS) and scope (object vs full scene) `[easy]`
Decide whether the output should be a continuous NeRF volume or a real-time 3DGS renderer, and whether you need single-object reconstruction or full scene/walkthrough navigation. This determines pipeline components and optimization strategy.

### Start from sparse-view or diffusion-guided lifting baseline `[medium]`
If you can obtain multiple views (even partially), use diffusion pseudo-observation ideas (e.g., Deceptive-NeRF/3DGS) to reduce required camera views; if only one image is available, use a single-view transformer/3DGS approach as the first stage and optionally refine with NeRF/consistency losses.

### Handle ambiguity with generative priors + consistency constraints `[medium]`
Adopt a denoising/diffusion training objective to jointly infer pose/geometry (for multi-view unknown pose) or distill a 2D diffusion model into a 3D representation for occluded/masked regions. Add depth/geometry priors and view-consistency constraints to reduce implausible completions.

### Refine and evaluate with standardized rendering-based metrics `[medium]`
Render novel views from the reconstructed 3D representation and evaluate photometric quality (PSNR/LPIPS/SSIM) plus geometric plausibility (when ground truth exists). Use occlusion-heavy test cases to measure failure modes.
