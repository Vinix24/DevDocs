#!/usr/bin/env python3
import sys
import logging
import signal
import json
import re
from pathlib import Path
from typing import Optional, Dict, List
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

from .document_structure import DocumentStructure

class MarkdownStore:
    """Manages markdown content and metadata."""
    
    def __init__(self, storage_path: str):
        self.base_path = Path(storage_path)
        self.content_cache = {}
        self.metadata_cache = {}
        self.structure_cache = {}  # Cache for parsed document structures
        
    async def get_content(self, file_id: str) -> str:
        """Get markdown content."""
        file_path = self.base_path / f"{file_id}.md"
        try:
            content = file_path.read_text(encoding='utf-8')
            # Parse and cache document structure
            if file_id not in self.structure_cache:
                structure = DocumentStructure()
                structure.parse_document(content)
                self.structure_cache[file_id] = structure
            return content
        except Exception as e:
            logger.error(f"Error reading content for {file_id}: {e}")
            return f"Error reading content: {str(e)}"

    async def get_section(self, file_id: str, section_id: str) -> str:
        """Get a specific section from a markdown file."""
        try:
            if file_id not in self.structure_cache:
                await self.get_content(file_id)  # This will parse and cache the structure
            
            structure = self.structure_cache[file_id]
            section = structure.get_section_by_id(section_id)
            
            if not section:
                return f"Section '{section_id}' not found in {file_id}"
                
            return f"Section: {section.title}\n\n{section.content}"
        except Exception as e:
            logger.error(f"Error getting section {section_id} from {file_id}: {e}")
            return f"Error getting section: {str(e)}"

    async def get_table_of_contents(self, file_id: str) -> str:
        """Get table of contents for a markdown file."""
        try:
            if file_id not in self.structure_cache:
                await self.get_content(file_id)  # This will parse and cache the structure
            
            structure = self.structure_cache[file_id]
            toc = structure.get_table_of_contents()
            
            result = [f"Table of Contents for {file_id}:"]
            for level, title, section_id in toc:
                indent = "  " * level
                result.append(f"{indent}- {title} [{section_id}]")
            
            return "\n".join(result)
        except Exception as e:
            logger.error(f"Error getting table of contents for {file_id}: {e}")
            return f"Error getting table of contents: {str(e)}"
        
    async def get_metadata(self, file_id: str) -> dict:
        """Get metadata as a dictionary."""
        file_path = self.base_path / f"{file_id}.json"
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading metadata for {file_id}: {e}")
            return {}
        
    async def get_index(self) -> str:
        """Get list of available files."""
        try:
            files = []
            for md_file in self.base_path.glob("*.md"):
                files.append(md_file.stem)
            return "\n".join(files)
        except Exception as e:
            logger.error(f"Error getting index: {e}")
            return f"Error getting index: {str(e)}"
        
    async def sync_file(self, file_id: str) -> str:
        """Force sync a file."""
        try:
            content = await self.get_content(file_id)
            metadata = await self.get_metadata(file_id)
            self.content_cache[file_id] = content
            self.metadata_cache[file_id] = metadata
            return f"Successfully synced {file_id}"
        except Exception as e:
            logger.error(f"Error syncing {file_id}: {e}")
            return f"Error syncing file: {str(e)}"

    async def list_files(self) -> str:
        """List all available markdown files."""
        try:
            files = []
            for md_file in self.base_path.glob("*.md"):
                files.append(f"- {md_file.stem}")
            if not files:
                return "No markdown files found"
            return "Available markdown files:\n" + "\n".join(files)
        except Exception as e:
            logger.error(f"Error listing files: {e}")
            return f"Error listing files: {str(e)}"

    async def read_file(self, file_id: str) -> str:
        """Read and return the content of a markdown file."""
        try:
            content = await self.get_content(file_id)
            metadata = await self.get_metadata(file_id)
            return f"""Content of {file_id}.md:

{content}

Metadata:
- Last modified: {metadata.get('timestamp', 'Unknown')}
- Word count: {metadata.get('stats', {}).get('wordCount', 'Unknown')}
- Character count: {metadata.get('stats', {}).get('charCount', 'Unknown')}
"""
        except Exception as e:
            logger.error(f"Error reading file {file_id}: {e}")
            return f"Error reading file: {str(e)}"

    async def search_files(self, query: str) -> str:
        """Search content across all markdown files."""
        try:
            results = []
            for md_file in self.base_path.glob("*.md"):
                file_id = md_file.stem
                content = await self.get_content(file_id)
                metadata = await self.get_metadata(file_id)
                
                if query.lower() in content.lower():
                    # Find the context around the match
                    lines = content.split('\n')
                    for i, line in enumerate(lines):
                        if query.lower() in line.lower():
                            context_start = max(0, i - 2)
                            context_end = min(len(lines), i + 3)
                            context = '\n'.join(lines[context_start:context_end])
                            
                            results.append(f"""Match in {file_id}.md:
Context:
{context}
---""")
            
            if not results:
                return f"No matches found for query: {query}"
            return "\n\n".join(results)
        except Exception as e:
            logger.error(f"Error searching files: {e}")
            return f"Error searching files: {str(e)}"

    async def search_by_tag(self, tag: str) -> str:
        """Search files by metadata tags."""
        try:
            results = []
            for json_file in self.base_path.glob("*.json"):
                file_id = json_file.stem
                metadata = await self.get_metadata(file_id)
                
                # Check both metadata.tags and top-level tags
                tags = metadata.get('metadata', {}).get('tags', []) + metadata.get('tags', [])
                
                if tag.lower() in [t.lower() for t in tags]:
                    results.append(f"""File: {file_id}.md
Tags: {', '.join(tags)}
Last modified: {metadata.get('timestamp', 'Unknown')}
---""")
            
            if not results:
                return f"No files found with tag: {tag}"
            return "\n\n".join(results)
        except Exception as e:
            logger.error(f"Error searching by tag: {e}")
            return f"Error searching by tag: {str(e)}"

    async def get_stats(self) -> str:
        """Get statistics about all markdown files."""
        try:
            total_files = 0
            total_words = 0
            total_chars = 0
            files_by_month = {}
            all_tags = set()
            
            for json_file in self.base_path.glob("*.json"):
                file_id = json_file.stem
                metadata = await self.get_metadata(file_id)
                
                total_files += 1
                total_words += metadata.get('stats', {}).get('wordCount', 0)
                total_chars += metadata.get('stats', {}).get('charCount', 0)
                
                # Extract month from timestamp
                timestamp = metadata.get('timestamp', '')
                if timestamp:
                    month = timestamp[:7]  # YYYY-MM
                    files_by_month[month] = files_by_month.get(month, 0) + 1
                
                # Collect all tags
                tags = metadata.get('metadata', {}).get('tags', []) + metadata.get('tags', [])
                all_tags.update(tags)
            
            stats = f"""Markdown Files Statistics:

Total Files: {total_files}
Total Words: {total_words}
Total Characters: {total_chars}

Files by Month:
{chr(10).join(f'- {month}: {count} files' for month, count in sorted(files_by_month.items()))}

All Tags:
{chr(10).join(f'- {tag}' for tag in sorted(all_tags))}
"""
            return stats
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return f"Error getting statistics: {str(e)}"

class MarkdownWatcher:
    """Watches for file system changes."""
    
    def __init__(self, store: MarkdownStore):
        self.store = store
        self.observer = Observer()
        
    async def on_modified(self, event):
        """Handle file modification events."""
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        if file_path.suffix in ['.md', '.json']:
            await self.store.sync_file(file_path.stem)

class FastMarkdownServer:
    """MCP server for markdown content management."""
    
    def __init__(self, storage_path: str):
        self.server = Server("fast-markdown")
        self.store = MarkdownStore(storage_path)
        self.watcher = MarkdownWatcher(self.store)
        self.setup_handlers()
        
    def setup_handlers(self):
        """Set up request handlers."""
        @self.server.list_resources()
        async def list_resources() -> list[types.Resource]:
            """List available resources."""
            files = []
            for md_file in self.store.base_path.glob("*.md"):
                file_id = md_file.stem
                files.append(
                    types.Resource(
                        uri=f"markdown://{file_id}/content",
                        name=f"Markdown content for {file_id}",
                        mimeType="text/markdown"
                    )
                )
            return files

        @self.server.read_resource()
        async def read_resource(uri: str) -> str:
            """Read resource content."""
            if not uri.startswith("markdown://"):
                raise ValueError(f"Invalid resource URI: {uri}")
            
            parts = uri.split("/")
            if len(parts) != 4 or parts[3] not in ["content", "metadata"]:
                raise ValueError(f"Invalid resource URI format: {uri}")
            
            file_id = parts[2]
            resource_type = parts[3]
            
            if resource_type == "content":
                return await self.store.get_content(file_id)
            else:
                return json.dumps(await self.store.get_metadata(file_id), indent=2)

        @self.server.list_tools()
        async def list_tools() -> list[types.Tool]:
            """List available tools."""
            return [
                types.Tool(
                    name="sync_file",
                    description="Force sync a specific file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_id": {
                                "type": "string",
                                "description": "ID of the file to sync (without .md extension)"
                            }
                        },
                        "required": ["file_id"]
                    }
                ),
                types.Tool(
                    name="get_status",
                    description="Get server status",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                types.Tool(
                    name="list_files",
                    description="List all available markdown files",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                types.Tool(
                    name="read_file",
                    description="Read the content of a markdown file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_id": {
                                "type": "string",
                                "description": "ID of the file to read (without .md extension)"
                            }
                        },
                        "required": ["file_id"]
                    }
                ),
                types.Tool(
                    name="search_files",
                    description="Search content across all markdown files",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query to find in markdown content"
                            }
                        },
                        "required": ["query"]
                    }
                ),
                types.Tool(
                    name="search_by_tag",
                    description="Search files by metadata tags",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "tag": {
                                "type": "string",
                                "description": "Tag to search for in file metadata"
                            }
                        },
                        "required": ["tag"]
                    }
                ),
                types.Tool(
                    name="get_stats",
                    description="Get statistics about all markdown files",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                types.Tool(
                    name="get_section",
                    description="Get a specific section from a markdown file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_id": {
                                "type": "string",
                                "description": "ID of the file (without .md extension)"
                            },
                            "section_id": {
                                "type": "string",
                                "description": "ID of the section to retrieve"
                            }
                        },
                        "required": ["file_id", "section_id"]
                    }
                ),
                types.Tool(
                    name="get_table_of_contents",
                    description="Get table of contents for a markdown file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_id": {
                                "type": "string",
                                "description": "ID of the file (without .md extension)"
                            }
                        },
                        "required": ["file_id"]
                    }
                )
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
            """Execute tool."""
            if name == "sync_file":
                file_id = arguments.get("file_id")
                if not file_id:
                    raise ValueError("file_id is required")
                result = await self.store.sync_file(file_id)
                return [types.TextContent(type="text", text=result)]
            elif name == "get_status":
                return [types.TextContent(type="text", text="Server is running and monitoring markdown files")]
            elif name == "list_files":
                result = await self.store.list_files()
                return [types.TextContent(type="text", text=result)]
            elif name == "read_file":
                file_id = arguments.get("file_id")
                if not file_id:
                    raise ValueError("file_id is required")
                result = await self.store.read_file(file_id)
                return [types.TextContent(type="text", text=result)]
            elif name == "search_files":
                query = arguments.get("query")
                if not query:
                    raise ValueError("query is required")
                result = await self.store.search_files(query)
                return [types.TextContent(type="text", text=result)]
            elif name == "search_by_tag":
                tag = arguments.get("tag")
                if not tag:
                    raise ValueError("tag is required")
                result = await self.store.search_by_tag(tag)
                return [types.TextContent(type="text", text=result)]
            elif name == "get_stats":
                result = await self.store.get_stats()
                return [types.TextContent(type="text", text=result)]
            elif name == "get_section":
                file_id = arguments.get("file_id")
                section_id = arguments.get("section_id")
                if not file_id or not section_id:
                    raise ValueError("file_id and section_id are required")
                result = await self.store.get_section(file_id, section_id)
                return [types.TextContent(type="text", text=result)]
            elif name == "get_table_of_contents":
                file_id = arguments.get("file_id")
                if not file_id:
                    raise ValueError("file_id is required")
                result = await self.store.get_table_of_contents(file_id)
                return [types.TextContent(type="text", text=result)]
            else:
                raise ValueError(f"Unknown tool: {name}")

    async def run(self):
        """Run the server."""
        logger.info("Starting server...")
        async with stdio_server() as streams:
            await self.server.run(
                streams[0],
                streams[1],
                self.server.create_initialization_options()
            )

def setup_logging():
    """Configure logging."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def handle_sigterm(signum, frame):
    """Handle SIGTERM signal."""
    logger.info("Received shutdown signal")
    sys.exit(0)

async def main() -> None:
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: fast-markdown-mcp <storage_path>")
        sys.exit(1)
    
    setup_logging()
    signal.signal(signal.SIGTERM, handle_sigterm)
    storage_path = sys.argv[1]
    
    try:
        server = FastMarkdownServer(storage_path)
        logger.info(f"Starting server with storage path: {storage_path}")
        await server.run()
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise
    finally:
        logger.info("Server shutdown complete")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())