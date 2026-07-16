FROM python:3.12-slim

# WeasyPrint needs these system libraries — this is exactly why Netlify's
# serverless functions don't work well for this and Railway (real container) does.
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Poppins font — same one used across every AM Studios graphic so far
RUN mkdir -p /usr/share/fonts/truetype/poppins && \
    curl -sL "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Regular.ttf" -o /usr/share/fonts/truetype/poppins/Poppins-Regular.ttf && \
    curl -sL "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf" -o /usr/share/fonts/truetype/poppins/Poppins-Bold.ttf && \
    curl -sL "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-SemiBold.ttf" -o /usr/share/fonts/truetype/poppins/Poppins-SemiBold.ttf && \
    curl -sL "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Medium.ttf" -o /usr/share/fonts/truetype/poppins/Poppins-Medium.ttf && \
    fc-cache -f

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PORT=8080
EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--timeout", "120", "app:flask_app"]
