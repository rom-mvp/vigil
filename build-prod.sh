#!/bin/bash
# Vigil Production Build Script
# Builds the GPU-accelerated Docker image for edge deployment

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🛡️  Vigil Production Build${NC}"
echo "================================"

# Configuration
IMAGE_NAME="${IMAGE_NAME:-vigil}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
REGISTRY="${REGISTRY:-}"  # e.g., ghcr.io/rom-mvp

# Full image name
if [ -n "$REGISTRY" ]; then
    FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
else
    FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"
fi

echo -e "${YELLOW}Building: ${FULL_IMAGE}${NC}"

# Check for NVIDIA Docker support (optional, for GPU)
if command -v nvidia-smi &> /dev/null; then
    echo -e "${GREEN}✓ NVIDIA GPU detected${NC}"
    GPU_AVAILABLE=true
else
    echo -e "${YELLOW}⚠ No GPU detected - image will support CPU fallback${NC}"
    GPU_AVAILABLE=false
fi

# Check for required files
echo ""
echo "Checking prerequisites..."

if [ ! -f "Dockerfile.prod" ]; then
    echo -e "${RED}✗ Dockerfile.prod not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Dockerfile.prod found${NC}"

if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}✗ requirements.txt not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ requirements.txt found${NC}"

if [ ! -d "src/vigil" ]; then
    echo -e "${RED}✗ src/vigil directory not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ src/vigil directory found${NC}"

# Check for models directory (warn if missing)
if [ ! -d "models" ]; then
    echo -e "${YELLOW}⚠ models/ directory not found - creating${NC}"
    mkdir -p models
fi

# Check for data directory (warn if missing)
if [ ! -d "data" ]; then
    echo -e "${YELLOW}⚠ data/ directory not found - creating${NC}"
    mkdir -p data
fi

if [ ! -f "data/threat_vectors.jsonl" ]; then
    echo -e "${YELLOW}⚠ data/threat_vectors.jsonl not found - container will use defaults${NC}"
fi

# Build the image
echo ""
echo "Building Docker image..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

docker build \
    -f Dockerfile.prod \
    -t "${FULL_IMAGE}" \
    --build-arg BUILDKIT_INLINE_CACHE=1 \
    .

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ Build successful!${NC}"
    echo ""
    echo "Image: ${FULL_IMAGE}"
    
    # Show image size
    IMAGE_SIZE=$(docker images "${FULL_IMAGE}" --format "{{.Size}}")
    echo "Size: ${IMAGE_SIZE}"
    
    # Test the image (basic smoke test)
    echo ""
    echo "Running smoke test..."
    
    # Test without GPU (basic python check)
    docker run --rm "${FULL_IMAGE}" python3 -c "
import sys
print(f'Python {sys.version}')

try:
    import onnxruntime as ort
    providers = ort.get_available_providers()
    print(f'ONNX Runtime providers: {providers}')
    if 'CUDAExecutionProvider' in providers:
        print('✓ GPU support available')
    else:
        print('⚠ GPU support not available (CPU only)')
except ImportError as e:
    print(f'✗ ONNX Runtime import failed: {e}')
    sys.exit(1)

try:
    from src.vigil.api_key_auth import APIKeyAuth
    print('✓ API Key Auth module loaded')
except ImportError as e:
    print(f'✗ API Key Auth import failed: {e}')
    sys.exit(1)

try:
    from src.vigil.token_meter import TokenMeter
    print('✓ Token Meter module loaded')
except ImportError as e:
    print(f'✗ Token Meter import failed: {e}')
    sys.exit(1)

try:
    from src.vigil.vector_engine import VectorScanner
    print('✓ Vector Scanner module loaded')
except ImportError as e:
    print(f'✗ Vector Scanner import failed: {e}')
    sys.exit(1)

print('')
print('✓ All smoke tests passed!')
"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Smoke test passed${NC}"
    else
        echo -e "${RED}✗ Smoke test failed${NC}"
        exit 1
    fi
    
    # Provide next steps
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${GREEN}Next Steps:${NC}"
    echo ""
    echo "1. Test locally:"
    if [ "$GPU_AVAILABLE" = true ]; then
        echo "   docker run --rm --gpus all -p 8000:8000 \\"
    else
        echo "   docker run --rm -p 8000:8000 \\"
    fi
    echo "     -e REDIS_URL=redis://host.docker.internal:6379 \\"
    echo "     -e AGENTSHIELD_URL=http://host.docker.internal:9000 \\"
    echo "     ${FULL_IMAGE}"
    echo ""
    echo "2. Push to registry:"
    if [ -n "$REGISTRY" ]; then
        echo "   docker push ${FULL_IMAGE}"
    else
        echo "   docker tag ${FULL_IMAGE} your-registry/${IMAGE_NAME}:${IMAGE_TAG}"
        echo "   docker push your-registry/${IMAGE_NAME}:${IMAGE_TAG}"
    fi
    echo ""
    echo "3. Deploy with docker-compose:"
    echo "   docker-compose -f docker-compose.prod.yml up -d"
    echo ""
    
    if [ "$GPU_AVAILABLE" = true ]; then
        echo -e "${YELLOW}Note: GPU deployment requires:${NC}"
        echo "  - nvidia-docker2 installed"
        echo "  - --gpus flag or deploy.resources.reservations in compose"
        echo ""
    fi
    
else
    echo -e "${RED}✗ Build failed${NC}"
    exit 1
fi
