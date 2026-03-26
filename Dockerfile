FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y curl ca-certificates

# Download and install the full certificate chain
RUN curl -o /tmp/ThawteEVRSACAG2.crt \
    https://cacerts.digicert.com/ThawteEVRSACAG2.crt \
    && openssl x509 -inform der -in /tmp/ThawteEVRSACAG2.crt \
       -out /usr/local/share/ca-certificates/ThawteEVRSACAG2.crt \
    && rm /tmp/ThawteEVRSACAG2.crt \
    && curl -o /usr/local/share/ca-certificates/DigiCertGlobalRootCA.crt \
       https://cacerts.digicert.com/DigiCertGlobalRootCA.crt.pem \
    && update-ca-certificates

WORKDIR /code/
COPY pyproject.toml .
COPY uv.lock .
ENV UV_PROJECT_ENVIRONMENT="/usr/local/"
RUN uv sync --all-groups --frozen

COPY src/ src
COPY tests/ tests
COPY scripts/ scripts
COPY deploy.sh .

ENV PYTHONIOENCODING="utf-8"
ENV PYTHONWARNINGS="ignore::UserWarning:_distutils_hack"
ENV REQUESTS_CA_BUNDLE="/etc/ssl/certs/ca-certificates.crt"
ENV SSL_CERT_FILE="/etc/ssl/certs/ca-certificates.crt"
ENV CURL_CA_BUNDLE="/etc/ssl/certs/ca-certificates.crt"

CMD ["python", "-u", "src/component.py"]
