FROM python:3.12-slim
ENV PYTHONIOENCODING utf-8

RUN apt-get update && apt-get install -y build-essential

COPY requirements.txt /code/requirements.txt
RUN pip install -r /code/requirements.txt

COPY . /code/
WORKDIR /code/

# Set the PYTHONWARNINGS environment variable
ENV PYTHONWARNINGS "ignore::UserWarning:_distutils_hack"

CMD ["python", "-u", "/code/src/component.py"]
