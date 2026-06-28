"""Prompt templates for the three agents — Host, Saboteur, Evaluator."""

from app.prompts.host import HOST_SYSTEM_PROMPT
from app.prompts.saboteur import SABOTEUR_SYSTEM_PROMPT
from app.prompts.evaluator import EVALUATOR_SYSTEM_PROMPT

__all__ = ["HOST_SYSTEM_PROMPT", "SABOTEUR_SYSTEM_PROMPT", "EVALUATOR_SYSTEM_PROMPT"]
