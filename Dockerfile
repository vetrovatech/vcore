# Use standard Python image for x86_64 with explicit platform
FROM --platform=linux/amd64 python:3.11-slim

# Install AWS Lambda Web Adapter for x86_64/AMD64 using explicit digest
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.8.4@sha256:9c44f6379a923316baeebdd06d728e48cb3a7bebc8f679a3a9a731aa6d1c9f77 /lambda-adapter /opt/extensions/lambda-adapter

# Set working directory
WORKDIR /app

# Install DejaVu fonts so the tax-invoice PDF can render the ₹ glyph
# (the default ReportLab Helvetica font lacks U+20B9 and renders it as
# a missing-glyph square). Slim package, ~3MB.
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

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
COPY static/ ./static/

# Expose port for Lambda Web Adapter
ENV PORT=8080

# Run Flask app with gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "1", "--timeout", "120", "--access-logfile", "-", "app:app"]

