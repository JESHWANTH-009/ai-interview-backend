# 1. Use lightweight Python image
FROM python:3.10-slim

# 2. Set working directory inside container
WORKDIR /backend

# 3. Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy all backend files, including serviceAccountKey.json
COPY . .

# 5. Expose FastAPI's default port
EXPOSE 8000

# 6. Start the FastAPI app using Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
