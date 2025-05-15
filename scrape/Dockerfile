# Base image
FROM python:3.12

# Set the working directory
WORKDIR /app

# Copy the requirements file
COPY scrape/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the base application, user has to provide parameters later
ENTRYPOINT ["python", "scrape.py"]
