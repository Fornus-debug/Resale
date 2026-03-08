FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY . .

RUN pip install requests playwright python-dotenv

CMD ["python", "resale_monitor.py"]
