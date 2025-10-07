FROM nixos/nix:latest

# Install Nix packages
RUN nix-channel --update && \
    nix-env -iA nixpkgs.python39 \
                nixpkgs.python39Packages.pip \
                nixpkgs.ffmpeg \
                nixpkgs.git

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies with break-system-packages flag
RUN pip3 install --break-system-packages -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Start command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
