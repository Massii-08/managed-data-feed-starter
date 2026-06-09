# Feedsmith — Managed Data Feed starter image.
FROM python:3.12-slim

# Keep Python output unbuffered and skip .pyc files in the container.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy the project and install it (pulls runtime deps from pyproject.toml).
COPY . /app
RUN pip install --no-cache-dir .

# FastAPI control plane.
EXPOSE 8000

CMD ["uvicorn", "feedsmith.api:app", "--host", "0.0.0.0", "--port", "8000"]
