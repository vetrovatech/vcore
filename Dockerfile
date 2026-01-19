# Use standard Python image for x86_64 with explicit platform
FROM --platform=linux/amd64 python:3.11-slim

# Install AWS Lambda Web Adapter for x86_64/AMD64 using explicit digest
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.8.4@sha256:9c44f6379a923316baeebdd06d728e48cb3a7bebc8f679a3a9a731aa6d1c9f77 /lambda-adapter /opt/extensions/lambda-adapter

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application code
COPY app.py .
COPY models.py .
COPY forms.py .
COPY config.py .
COPY utils/ ./utils/
COPY templates/ ./templates/

# Expose port for Lambda Web Adapter
ENV PORT=8080

# Run Flask app with gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "1", "--timeout", "30", "app:app"]

