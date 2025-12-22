provider "aws" {
  region = "us-east-1"
}

# 1. Security Group (The Firewall)
resource "aws_security_group" "vigil_sg" {
  name        = "vigil_sg"
  description = "Allow Vigil Traffic"

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  # Allow SSH for you only
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # WARNING: Replace with your IP for safety
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# 2. The Server (EC2)
resource "aws_instance" "vigil_server" {
  ami           = "ami-0c7217cdde317cfec" # Ubuntu 22.04 LTS
  instance_type = "t3.medium"             # 2 vCPU, 4GB RAM (Good for ML inference)
  security_groups = [aws_security_group.vigil_sg.name]
  key_name = "your-ssh-key-name"          # <--- Change this

  user_data = <<-EOF
              #!/bin/bash
              apt-get update
              apt-get install -y docker.io docker-compose
              git clone https://github.com/rom-mvp/vigil.git /home/ubuntu/vigil
              cd /home/ubuntu/vigil
              
              # Build and Run in Detached Mode
              docker-compose up --build -d
              EOF

  tags = {
    Name = "Vigil-Production-Firewall"
  }
}

output "public_ip" {
  value = aws_instance.vigil_server.public_ip
}
