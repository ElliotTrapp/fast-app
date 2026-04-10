FROM python:3.12-slim
WORKDIR /app
# Copy everything needed for installation
COPY pyproject.toml README.md ./
COPY src/ ./src/
# Install Python dependencies
RUN pip install --no-cache-dir .
# Expose port
EXPOSE 8000
# Run server
CMD ["fast-app", "serve"]