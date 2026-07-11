"""Compatibility import for the chat feature's application workflow.

New routes and feature code import :mod:`features.chat.application` directly.
This module remains temporarily so existing integrations retain their import
path while the flatter ``services`` namespace is retired gradually.
"""

from features.chat.application import send_public_chat_message


__all__ = ["send_public_chat_message"]
