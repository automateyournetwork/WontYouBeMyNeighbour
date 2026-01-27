"""
Network Documentation Generator Module

This module provides automated network documentation generation including:
- Topology diagrams
- IP addressing plans
- Protocol configuration summaries
- Interface descriptions
- Export to Markdown, HTML, and PDF formats

Classes:
    DocumentFormat: Enum of supported document formats
    DocumentSection: Enum of document sections
    DocumentTemplate: Template definitions for documents
    NetworkDocument: A generated network document
    DocumentGenerator: Main documentation generation engine

Functions:
    get_document_generator: Get the singleton DocumentGenerator instance
    generate_documentation: Generate documentation for a network
    export_document: Export a document to a specific format
    get_available_templates: Get list of available document templates
"""

from .document_generator import (
    DocumentFormat,
    DocumentSection,
    DocumentTemplate,
    NetworkDocument,
    DocumentGenerator,
)


# Singleton instance
_generator_instance = None


def get_document_generator() -> DocumentGenerator:
    """Get the singleton DocumentGenerator instance."""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = DocumentGenerator()
    return _generator_instance


def generate_documentation(
    network_name: str = None,
    sections: list = None,
    template: str = None
) -> NetworkDocument:
    """Generate documentation for a network."""
    generator = get_document_generator()
    return generator.generate(
        network_name=network_name,
        sections=sections,
        template=template
    )


def export_document(
    document: NetworkDocument,
    format: DocumentFormat,
    output_path: str = None
) -> str:
    """Export a document to a specific format."""
    generator = get_document_generator()
    return generator.export(document, format, output_path)


def get_available_templates() -> list:
    """Get list of available document templates."""
    generator = get_document_generator()
    return generator.get_templates()


__all__ = [
    'DocumentFormat',
    'DocumentSection',
    'DocumentTemplate',
    'NetworkDocument',
    'DocumentGenerator',
    'get_document_generator',
    'generate_documentation',
    'export_document',
    'get_available_templates',
]
