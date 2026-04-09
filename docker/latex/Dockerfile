FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# TeX Live subset que cubre el 95% de papers académicos (~1.5 GB vs 5 GB de texlive-full)
RUN apt-get update && apt-get install -y \
    texlive-latex-extra \
    texlive-science \
    texlive-publishers \
    texlive-bibtex-extra \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    texlive-lang-european \
    biber \
    latexmk \
    python3 \
    python3-pip \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip3 install fastapi uvicorn python-multipart

WORKDIR /app
COPY service.py .

# Usuario sin privilegios para seguridad
RUN useradd -m latexuser
USER latexuser

# Directorio de salida dentro del home del usuario (siempre tiene permisos)
RUN mkdir -p /home/latexuser/outputs

EXPOSE 8001

CMD ["python3", "-m", "uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8001"]
