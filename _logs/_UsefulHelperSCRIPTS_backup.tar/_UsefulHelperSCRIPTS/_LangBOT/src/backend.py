from typing import TypedDict
from langgraph.graph import StateGraph, END
from src.microservices._NeuralServiceMS import NeuralServiceMS
from src.microservices._VectorFactoryMS import VectorFactoryMS
from src.microservices._CognitiveMemoryMS import CognitiveMemoryMS

class AgentState(TypedDict):
    question: str
    context: str
    history: str
    answer: str

class LangBotBackend:
    def __init__(self):
        # 32GB RAM allows these to stay initialized, but we limit execution concurrency
        self.neural = NeuralServiceMS()
        self.memory = CognitiveMemoryMS()
        self.factory = VectorFactoryMS()
        
        # Initialize ChromaDB via your Factory [cite: 138, 140]
        self.ltm = self.factory.create('chroma', {'path': './chroma_db', 'collection': 'langbot_ltm'})
        self.workflow = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("retrieve", self._retrieve_node)
        workflow.add_node("generate", self._generate_node)
        
        workflow.set_entry_point("retrieve")
        workflow.add_edge("retrieve", "generate")
        workflow.add_edge("generate", END)
        return workflow.compile()

    def _retrieve_node(self, state: AgentState):
        # NeuralService handles the local embedding call [cite: 105]
        emb = self.neural.get_embedding(state["question"])
        results = self.ltm.search(emb, k=3) if emb else []
        context = "\n".join([r.get('content', '') for r in results])
        return {"context": context, "history": self.memory.get_context()}

    def _generate_node(self, state: AgentState):
        prompt = f"Context: {state['context']}\nHistory: {state['history']}\nUser: {state['question']}"

        # Persist the FULL turn so history stays coherent next prompt.
        # (We add the user turn here so the history used for THIS prompt
        #  is still the prior context captured in _retrieve_node.)
        self.memory.add_entry("user", state["question"])

        response = self.neural.request_inference(prompt, tier="smart")

        self.memory.add_entry("assistant", response)
        self.memory.commit_turn()  # optional but matches your design :contentReference[oaicite:4]{index=4}
        return {"answer": response}
