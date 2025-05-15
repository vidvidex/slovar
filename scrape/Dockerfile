# Base image
FROM python:3.14

# Set the working directory
WORKDIR /app

# Copy the requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the base application, user has to provide parameters later
CMD ["python", "scrape.py"]

