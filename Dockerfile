# Set python version
ARG BASE_CONTAINER=python:3.11

# Set the base image 
FROM --platform=linux/amd64 $BASE_CONTAINER

# dont write pyc files
ENV PYTHONDONTWRITEBYTECODE 1
# dont buffer to stdout/stderr
ENV PYTHONUNBUFFERED 1

# Sets the user name to use when running the image.
USER root
RUN apt update && \
    apt install --no-install-recommends -y build-essential gcc && \
    apt clean && rm -rf /var/lib/apt/lists/* \
    && pip install poetry \
    && poetry config virtualenvs.in-project true


# Make a directory for app
WORKDIR /app

# Install dependencies
COPY ./poetry.lock ./pyproject.toml ./

# Copy source code
COPY . .

RUN poetry install --only main
RUN ["chmod", "+x", "/app/run_migartions.sh"]

# Run the application
CMD ["./.venv/bin/python", "bot"]
