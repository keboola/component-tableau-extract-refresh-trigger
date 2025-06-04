FROM python:3.12-slim
ENV PYTHONIOENCODING utf-8

COPY . /code/

# install gcc to be able to build packages - e.g. required by regex, dateparser, also required for pandas
RUN apt-get update && apt-get install -y curl ca-certificates

RUN pip install flake8

RUN pip install -r /code/requirements.txt

# Download and install the intermediate CA certificate directly
RUN curl -o /usr/local/share/ca-certificates/ThawteEVRSACAG2.crt \
    https://cacerts.digicert.com/ThawteEVRSACAG2.crt \
    && openssl x509 -inform der -in /usr/local/share/ca-certificates/ThawteEVRSACAG2.crt \
       -out /usr/local/share/ca-certificates/ThawteEVRSACAG2.pem \
    && mv /usr/local/share/ca-certificates/ThawteEVRSACAG2.pem \
          /usr/local/share/ca-certificates/ThawteEVRSACAG2.crt \
    && update-ca-certificates

WORKDIR /code/

# Set the PYTHONWARNINGS environment variable
ENV PYTHONWARNINGS "ignore::UserWarning:_distutils_hack"

CMD ["python", "-u", "/code/src/component.py"]
