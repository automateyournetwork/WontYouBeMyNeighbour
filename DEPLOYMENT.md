# Ralph Agentic Network Router - Deployment Guide

This guide covers deploying Ralph in various environments.

## Quick Start with Docker

### 1. Set up environment variables

```bash
cp .env.example .env
# Edit .env and add your LLM API keys
```

### 2. Build and run

```bash
# Run API server
docker-compose -f docker-compose.agentic.yml up ralph-api

# Or run demo
docker-compose -f docker-compose.agentic.yml --profile demo up ralph-demo

# Or run CLI
docker-compose -f docker-compose.agentic.yml --profile cli up ralph-cli
```

### 3. Access Ralph

- **API**: http://localhost:8080
- **API Docs**: http://localhost:8080/docs
- **Health**: http://localhost:8080/health

## Deployment Options

### Option 1: Docker (Recommended)

**Advantages:**
- Isolated environment
- Easy scaling
- Consistent across platforms

**Steps:**

```bash
# Build image
docker build -f Dockerfile.agentic -t ralph:latest .

# Run API server
docker run -d \
  --name ralph-api \
  -p 8080:8080 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e RALPH_ID=ralph-prod-1 \
  ralph:latest \
  python -m wontyoubemyneighbor.agentic api

# Check logs
docker logs -f ralph-api

# Stop
docker stop ralph-api
```

### Option 2: Native Python

**Requirements:**
- Python 3.11+
- pip

**Steps:**

```bash
# Install dependencies
pip install -r wontyoubemyneighbor/agentic/requirements.txt

# Set environment variables
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."

# Run API server
python -m wontyoubemyneighbor.agentic api --port 8080

# Or run CLI
python -m wontyoubemyneighbor.agentic cli

# Or run demo
python -m wontyoubemyneighbor.agentic demo
```

### Option 3: Systemd Service (Linux)

Create `/etc/systemd/system/ralph.service`:

```ini
[Unit]
Description=Ralph Agentic Network Router
After=network.target

[Service]
Type=simple
User=ralph
WorkingDirectory=/opt/ralph
Environment="ANTHROPIC_API_KEY=sk-ant-..."
Environment="PYTHONPATH=/opt/ralph"
ExecStart=/usr/bin/python3 -m wontyoubemyneighbor.agentic api --port 8080
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ralph
sudo systemctl start ralph
sudo systemctl status ralph
```

## Multi-Agent Deployment

Deploy multiple Ralph instances for distributed consensus:

```bash
# Start two Ralph instances
docker-compose -f docker-compose.agentic.yml --profile multi-agent up

# Ralph 1: http://localhost:8080
# Ralph 2: http://localhost:8081
```

Configure gossip peers via API:

```bash
# Tell Ralph 1 about Ralph 2
curl -X POST http://localhost:8080/api/gossip/peers \
  -H "Content-Type: application/json" \
  -d '{
    "peer_id": "ralph-api-2",
    "address": "ralph-api-2",
    "port": 8080
  }'

# Tell Ralph 2 about Ralph 1
curl -X POST http://localhost:8081/api/gossip/peers \
  -H "Content-Type: application/json" \
  -d '{
    "peer_id": "ralph-api-1",
    "address": "ralph-api",
    "port": 8080
  }'
```

## Integration with OSPF/BGP

### Connect to real network protocols

```python
from wontyoubemyneighbor.agentic.integration.bridge import AgenticBridge
from wontyoubemyneighbor.agentic.integration.ospf_connector import OSPFConnector
from wontyoubemyneighbor.agentic.integration.bgp_connector import BGPConnector

# Import your actual OSPF/BGP implementations
from wontyoubemyneighbor.ospfv3.interface import OSPFv3Interface
from wontyoubemyneighbor.bgp.speaker import BGPSpeaker

# Create OSPF interface
ospf_interface = OSPFv3Interface(
    interface_name="eth0",
    router_id="1.1.1.1",
    area_id="0.0.0.0"
)

# Create BGP speaker
bgp_speaker = BGPSpeaker(
    local_as=65001,
    router_id="1.1.1.1"
)

# Create agentic bridge
bridge = AgenticBridge(
    ralph_id="ralph-production",
    claude_key="sk-ant-...",
    autonomous_mode=False
)

# Connect protocols
bridge.set_ospf_connector(OSPFConnector(ospf_interface))
bridge.set_bgp_connector(BGPConnector(bgp_speaker))

# Initialize and start
await bridge.initialize()
await bridge.start()
```

## Production Configuration

### Security

1. **API Keys**: Store in secrets manager (AWS Secrets Manager, HashiCorp Vault)
2. **HTTPS**: Use reverse proxy (nginx, traefik) with TLS
3. **Authentication**: Add API key authentication to endpoints
4. **Network**: Restrict access via firewall rules

### Monitoring

1. **Metrics**: Expose Prometheus metrics
2. **Logging**: Ship logs to centralized logging (ELK, Splunk)
3. **Alerts**: Configure alerts for anomalies, failures

### High Availability

1. **Load Balancer**: Distribute requests across multiple Ralph instances
2. **State Sync**: Use consensus protocol for distributed state
3. **Health Checks**: Configure readiness and liveness probes

### Example nginx reverse proxy

```nginx
upstream ralph {
    server ralph-api-1:8080;
    server ralph-api-2:8080;
}

server {
    listen 443 ssl;
    server_name ralph.example.com;

    ssl_certificate /etc/ssl/certs/ralph.crt;
    ssl_certificate_key /etc/ssl/private/ralph.key;

    location / {
        proxy_pass http://ralph;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Scaling

### Horizontal Scaling

Deploy multiple Ralph instances behind a load balancer:

```bash
docker-compose -f docker-compose.agentic.yml scale ralph-api=3
```

### Resource Limits

Set memory and CPU limits:

```yaml
# docker-compose.agentic.yml
services:
  ralph-api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
```

## Kubernetes Deployment

Example Kubernetes deployment:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ralph-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ralph
  template:
    metadata:
      labels:
        app: ralph
    spec:
      containers:
      - name: ralph
        image: ralph:latest
        ports:
        - containerPort: 8080
        env:
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: ralph-secrets
              key: anthropic-api-key
        - name: RALPH_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        resources:
          limits:
            memory: "4Gi"
            cpu: "2"
          requests:
            memory: "2Gi"
            cpu: "1"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: ralph-api
spec:
  selector:
    app: ralph
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
  type: LoadBalancer
```

## Troubleshooting

### Check health

```bash
curl http://localhost:8080/health
```

### View logs

```bash
# Docker
docker logs ralph-api

# Systemd
sudo journalctl -u ralph -f
```

### Test connectivity

```bash
# Test API
curl http://localhost:8080/api/statistics

# Test query
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is my network status?"}'
```

### Common Issues

1. **API key errors**: Verify keys are set correctly in environment
2. **Port conflicts**: Change port with `--port` flag
3. **Memory issues**: Increase container/system memory limits
4. **Timeout errors**: Increase LLM timeout settings

## Backup and Recovery

### State backup

```bash
# Export conversation history
curl http://localhost:8080/api/conversation/history > backup.json

# Export network snapshots
# (Implement custom endpoint if needed)
```

### Recovery

```bash
# Import conversation history
# (Implement custom endpoint if needed)
```

## Updating

### Docker

```bash
# Pull latest image
docker pull ralph:latest

# Restart containers
docker-compose -f docker-compose.agentic.yml down
docker-compose -f docker-compose.agentic.yml up -d
```

### Native

```bash
git pull
pip install -r wontyoubemyneighbor/agentic/requirements.txt --upgrade
sudo systemctl restart ralph
```

## Support

For issues and questions:
- Documentation: `wontyoubemyneighbor/agentic/README.md`
- Examples: `examples/agentic_demo.py`
- Tests: `wontyoubemyneighbor/agentic/tests/`
