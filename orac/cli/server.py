"""
CLI command for starting the Orac API server.
"""

import argparse


def add_server_parser(subparsers):
    """Add server resource parser."""
    server_parser = subparsers.add_parser(
        'server',
        help='Start the HTTP API server',
        description='Start the Orac HTTP API server with web frontend'
    )

    server_parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='Host to bind to (default: 0.0.0.0)'
    )
    server_parser.add_argument(
        '--port', '-p',
        type=int,
        default=8000,
        help='Port to bind to (default: 8000)'
    )
    server_parser.add_argument(
        '--reload',
        action='store_true',
        help='Enable auto-reload for development'
    )

    return server_parser


def handle_server_commands(args, remaining):
    """Handle server commands."""
    start_server(
        host=getattr(args, 'host', '0.0.0.0'),
        port=getattr(args, 'port', 8000),
        reload=getattr(args, 'reload', False)
    )


def start_server(host: str = '0.0.0.0', port: int = 8000, reload: bool = False):
    """Start the API server."""
    import uvicorn

    print(f"Starting Orac API server at http://{host}:{port}")
    print(f"Frontend available at http://{host}:{port}/")
    print(f"API docs available at http://{host}:{port}/docs")
    print()

    uvicorn.run(
        "orac.api:app",
        host=host,
        port=port,
        reload=reload
    )
