FROM python:3.12-slim
WORKDIR /app
COPY . .
ENV PORT=8080 DATA_FILE=/data/phonemail.json
EXPOSE 8080
CMD ["python", "server.py"]
