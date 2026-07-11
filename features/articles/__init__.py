"""Article feature boundary for public reads and content persistence.

Submodules stay lazily imported so legacy article services can depend on the
content-store helper without creating an import cycle with page workflows.
"""
