"""
RubberBand REST API Server

FastAPI-based REST API for natural language network management.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import asyncio

try:
    from fastapi import FastAPI, HTTPException, BackgroundTasks
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    # Provide stubs for type hints
    class BaseModel:
        pass
    class FastAPI:
        pass


class QueryRequest(BaseModel):
    """Natural language query request"""
    query: str
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 4000


class QueryResponse(BaseModel):
    """Query response"""
    response: str
    intent_type: Optional[str] = None
    confidence: Optional[float] = None
    execution_time_ms: Optional[float] = None


class ActionRequest(BaseModel):
    """Direct action request"""
    action_type: str
    parameters: Dict[str, Any]
    skip_safety: bool = False


class ActionResponse(BaseModel):
    """Action execution response"""
    action_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ProposalRequest(BaseModel):
    """Consensus proposal request"""
    consensus_type: str
    description: str
    parameters: Dict[str, Any]
    required_votes: int = 2


class VoteRequest(BaseModel):
    """Consensus vote request"""
    proposal_id: str
    vote: str  # approve, reject, abstain
    reason: Optional[str] = None


class RubberBandAPI:
    """
    RubberBand REST API

    Provides HTTP endpoints for:
    - Natural language queries
    - Direct actions
    - State inspection
    - Multi-agent coordination
    - Statistics and monitoring
    """

    def __init__(self, agentic_bridge):
        """
        Initialize API with agentic bridge.

        Args:
            agentic_bridge: Instance of AgenticBridge
        """
        if not FASTAPI_AVAILABLE:
            raise RuntimeError("FastAPI not installed. Install with: pip install fastapi uvicorn")

        self.bridge = agentic_bridge
        self.app = FastAPI(
            title="RubberBand Network Agent API",
            description="Natural language interface for network management",
            version="1.0.0"
        )

        # Add CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Register routes
        self._register_routes()

    def _register_routes(self):
        """Register API routes"""

        @self.app.get("/")
        async def root():
            """API root"""
            return {
                "service": "RubberBand Network Agent",
                "rubberband_id": self.bridge.rubberband_id,
                "version": "1.0.0",
                "endpoints": {
                    "query": "/api/query",
                    "action": "/api/action",
                    "state": "/api/state",
                    "statistics": "/api/statistics",
                    "proposals": "/api/proposals",
                    "health": "/health"
                }
            }

        @self.app.get("/health")
        async def health():
            """Health check"""
            return {
                "status": "healthy",
                "rubberband_id": self.bridge.rubberband_id,
                "timestamp": datetime.utcnow().isoformat()
            }

        @self.app.post("/api/query", response_model=QueryResponse)
        async def query(request: QueryRequest):
            """Process natural language query"""
            import time
            start_time = time.time()

            try:
                response = await self.bridge.query(request.query)

                execution_time = (time.time() - start_time) * 1000

                return QueryResponse(
                    response=response,
                    execution_time_ms=execution_time
                )

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/action", response_model=ActionResponse)
        async def execute_action(request: ActionRequest):
            """Execute direct action"""
            try:
                result = await self.bridge.executor.execute_action(
                    action_type=request.action_type,
                    parameters=request.parameters,
                    skip_safety=request.skip_safety
                )

                return ActionResponse(
                    action_id=result.action_id,
                    status=result.status.value,
                    result=result.result,
                    error=result.error
                )

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/state")
        async def get_state():
            """Get current network state"""
            try:
                await self.bridge.state_manager.update_state()
                return {
                    "summary": self.bridge.state_manager.get_state_summary(),
                    "context": self.bridge.state_manager.get_llm_context(),
                    "metrics": self.bridge.state_manager._compute_metrics(),
                    "timestamp": datetime.utcnow().isoformat()
                }

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/state/ospf")
        async def get_ospf_state():
            """Get OSPF state"""
            try:
                await self.bridge.state_manager.update_state()
                return self.bridge.state_manager._current_ospf_state

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/state/bgp")
        async def get_bgp_state():
            """Get BGP state"""
            try:
                await self.bridge.state_manager.update_state()
                return self.bridge.state_manager._current_bgp_state

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/state/routes")
        async def get_routes():
            """Get routing table"""
            try:
                await self.bridge.state_manager.update_state()
                return {
                    "routes": self.bridge.state_manager._current_routing_table,
                    "count": len(self.bridge.state_manager._current_routing_table)
                }

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/statistics")
        async def get_statistics():
            """Get comprehensive statistics"""
            try:
                return self.bridge.get_statistics()

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/analytics/report")
        async def get_analytics_report():
            """Get analytics report"""
            try:
                report = self.bridge.analytics.generate_report()
                return {"report": report, "timestamp": datetime.utcnow().isoformat()}

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/analytics/anomalies")
        async def detect_anomalies():
            """Detect network anomalies"""
            try:
                network_state = self.bridge.state_manager.get_llm_context()
                anomalies = await self.bridge.decision_engine.detect_anomalies(network_state)
                return {"anomalies": anomalies, "count": len(anomalies)}

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/proposals")
        async def create_proposal(request: ProposalRequest):
            """Create consensus proposal"""
            try:
                from ..multi_agent.consensus import ConsensusType

                proposal = self.bridge.consensus.create_proposal(
                    consensus_type=ConsensusType(request.consensus_type),
                    description=request.description,
                    parameters=request.parameters,
                    required_votes=request.required_votes
                )

                return proposal.to_dict()

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/proposals")
        async def list_proposals():
            """List active proposals"""
            try:
                return {"proposals": self.bridge.consensus.get_active_proposals()}

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/proposals/{proposal_id}")
        async def get_proposal(proposal_id: str):
            """Get proposal status"""
            try:
                status = self.bridge.consensus.get_proposal_status(proposal_id)
                if not status:
                    raise HTTPException(status_code=404, detail="Proposal not found")
                return status

            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/proposals/{proposal_id}/vote")
        async def vote_on_proposal(proposal_id: str, request: VoteRequest):
            """Vote on proposal"""
            try:
                from ..multi_agent.consensus import VoteType

                success = self.bridge.consensus.vote(
                    proposal_id=proposal_id,
                    vote=VoteType(request.vote),
                    reason=request.reason
                )

                if not success:
                    raise HTTPException(status_code=404, detail="Proposal not found or expired")

                return {"success": True, "proposal_id": proposal_id}

            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/actions/history")
        async def get_action_history(limit: int = 50):
            """Get action execution history"""
            try:
                return {"actions": self.bridge.executor.get_action_history(limit)}

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/actions/pending")
        async def get_pending_actions():
            """Get actions pending approval"""
            try:
                pending = self.bridge.executor.get_pending_actions()
                return {"actions": [a.to_dict() for a in pending]}

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/actions/{action_id}/approve")
        async def approve_action(action_id: str):
            """Approve pending action"""
            try:
                success = self.bridge.executor.approve_action(action_id)
                if not success:
                    raise HTTPException(status_code=404, detail="Action not found")
                return {"success": True, "action_id": action_id}

            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/actions/{action_id}/reject")
        async def reject_action(action_id: str, reason: str = "User rejected"):
            """Reject pending action"""
            try:
                success = self.bridge.executor.reject_action(action_id, reason)
                if not success:
                    raise HTTPException(status_code=404, detail="Action not found")
                return {"success": True, "action_id": action_id}

            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/conversation/history")
        async def get_conversation_history():
            """Get LLM conversation history"""
            try:
                return {
                    "history": self.bridge.llm.get_conversation_history(),
                    "turns": self.bridge.llm.current_turn,
                    "max_turns": self.bridge.llm.max_turns
                }

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/conversation/reset")
        async def reset_conversation():
            """Reset conversation history"""
            try:
                self.bridge.llm.reset_conversation()
                return {"success": True, "message": "Conversation reset"}

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))


def create_api_server(agentic_bridge, host: str = "0.0.0.0", port: int = 8080):
    """
    Create and configure RubberBand API server.

    Args:
        agentic_bridge: Instance of AgenticBridge
        host: Host to bind to
        port: Port to listen on

    Returns:
        Tuple of (RubberBandAPI, uvicorn server config)
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI not installed. Install with: pip install fastapi uvicorn")

    api = RubberBandAPI(agentic_bridge)

    # Return API instance and server config
    return api, {
        "app": api.app,
        "host": host,
        "port": port,
        "log_level": "info"
    }
