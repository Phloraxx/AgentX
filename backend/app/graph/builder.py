"""Build and compile the LangGraph state machine."""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from app.graph.state import SessionState
from app.graph import nodes, edges


def build_graph():
    """Build the AgentX state graph.

    Flow:
        host_setup → host_present → [INTERRUPT: student writes code]
        → saboteur_inject → [INTERRUPT: student submits fix]
        → host_run_fix → evaluator_score → adjust (loop) or END
    """
    g = StateGraph(SessionState)

    # Nodes
    g.add_node("host_setup", nodes.host_setup)
    g.add_node("host_present", nodes.host_present)
    g.add_node("saboteur_inject", nodes.saboteur_inject)
    g.add_node("student_fix_await", nodes.student_fix_await)
    g.add_node("host_run_fix", nodes.host_run_fix)
    g.add_node("evaluator_score", nodes.evaluator_score)
    g.add_node("adjust", nodes.adjust)
    g.add_node("finish", nodes.finish)

    # Edges
    g.set_entry_point("host_setup")
    g.add_edge("host_setup", "host_present")
    g.add_edge("host_present", "saboteur_inject")
    g.add_edge("saboteur_inject", "student_fix_await")
    g.add_edge("student_fix_await", "host_run_fix")
    g.add_edge("host_run_fix", "evaluator_score")

    # After evaluation: loop back or finish
    g.add_conditional_edges(
        "evaluator_score",
        edges.round_or_done,
        {"adjust": "adjust", "done": "finish"},
    )
    g.add_edge("adjust", "host_setup")
    g.add_edge("finish", END)

    # Two interrupts: before saboteur_inject (student writes code) and
    # before student_fix_await (student submits fix)
    return g.compile(
        interrupt_before=["saboteur_inject", "student_fix_await"],
        checkpointer=MemorySaver(),
    )
