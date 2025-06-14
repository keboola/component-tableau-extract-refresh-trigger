FROM python:3.12-slim
ENV PYTHONIOENCODING utf-8

COPY . /code/

# install gcc to be able to build packages - e.g. required by regex, dateparser, also required for pandas
RUN apt-get update && apt-get install -y curl ca-certificates

RUN pip install flake8

RUN pip install -r /code/requirements.txt

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

# Set the PYTHONWARNINGS environment variable
ENV PYTHONWARNINGS "ignore::UserWarning:_distutils_hack"

# Set SSL certificate environment variables to ensure Python uses system certificates
ENV REQUESTS_CA_BUNDLE="/etc/ssl/certs/ca-certificates.crt"
ENV SSL_CERT_FILE="/etc/ssl/certs/ca-certificates.crt"
ENV CURL_CA_BUNDLE="/etc/ssl/certs/ca-certificates.crt"

CMD ["python", "-u", "/code/src/component.py"]
