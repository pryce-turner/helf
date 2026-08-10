"""MCP server exposing the Helf database to any MCP client.

Deliberately importing nothing from the rest of `app` except `config`
(ADR-0002): the agent and the application share a *file*, not a code path.
"""
