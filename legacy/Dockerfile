FROM python:3.9-slim
WORKDIR /app
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download en_core_web_sm
COPY firewall_engine.py .
COPY pii_engine.py .   
COPY local_server.py .
EXPOSE 8000
CMD ["python", "local_server.py"]
