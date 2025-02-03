import io
import os
import subprocess
import re
import traceback
from contextlib import redirect_stdout, redirect_stderr
from typing import  List

from mcp.server.fastmcp import FastMCP, Context
import mcp.types as types

# Initialize with settings
mcp = FastMCP(
    "python-repl",
    debug=True,  # Enable debug mode
    warn_on_duplicate_tools=True,  # Warn if we try to register duplicate tools
)

# Shared namespace for all executions
global_namespace = {
    "__builtins__": __builtins__,
}

@mcp.tool()
async def execute_python(ctx: Context, code: str, reset: bool = False) -> List[types.TextContent]:
    """Execute Python code and return the output. Variables persist between executions."""
    global global_namespace
    
    if reset:
        global_namespace.clear()
        global_namespace["__builtins__"] = __builtins__
        return [types.TextContent(type="text", text="Python session reset. All variables cleared.")]

    stdout = io.StringIO()
    stderr = io.StringIO()
    
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exec(code, global_namespace)
        
        output = stdout.getvalue()
        errors = stderr.getvalue()
        
        result = ""
        if output:
            result += f"Output:\n{output}"
        if errors:
            result += f"\nErrors:\n{errors}"
        if not output and not errors:
            try:
                last_line = code.strip().split('\n')[-1]
                last_value = eval(last_line, global_namespace)
                result = f"Result: {repr(last_value)}"
            except (SyntaxError, ValueError, NameError):
                result = "Code executed successfully (no output)"
        
        return [types.TextContent(type="text", text=result)]
            
    except Exception:
        error_msg = f"Error executing code:\n{traceback.format_exc()}"
        return [types.TextContent(type="text", text=error_msg)]

@mcp.tool()
async def install_package(ctx: Context, package: str) -> List[types.TextContent]:
    """Install a Python package using uv"""
    if not re.match("^[A-Za-z0-9][A-Za-z0-9._-]*$", package):
        return [types.TextContent(type="text", text=f"Invalid package name: {package}")]
    
    try:
        ctx.info(f"Installing package: {package}")
        process = subprocess.run(
            ["uv", "pip", "install", package],
            capture_output=True,
            text=True,
            check=True
        )

        if process.returncode != 0:
            return [types.TextContent(type="text", text=f"Failed to install package: {process.stderr}")]
        
        try:
            exec(f"import {package.split('[')[0]}", global_namespace)
            return [types.TextContent(type="text", text=f"Successfully installed and imported {package}")]
        except ImportError as e:
            return [types.TextContent(type="text", text=f"Package installed but import failed: {str(e)}")]
            
    except subprocess.CalledProcessError as e:
        return [types.TextContent(type="text", text=f"Failed to install package:\n{e.stderr}")]

@mcp.tool()
async def list_variables(ctx: Context) -> List[types.TextContent]:
    """List all variables in the current session"""
    vars_dict = {
        k: repr(v) for k, v in global_namespace.items() 
        if not k.startswith('_') and k != '__builtins__'
    }
    
    if not vars_dict:
        return [types.TextContent(type="text", text="No variables in current session.")]
    
    var_list = "\n".join(f"{k} = {v}" for k, v in vars_dict.items())
    return [types.TextContent(type="text", text=f"Current session variables:\n\n{var_list}")]

async def handle_initialized(ctx: Context):
    """Handle initialization after connection is established"""
    try:
        # Subscribe to root changes if we're interested
        ctx.info("Setting up root monitoring...")
        
        roots_result = await ctx.session.list_roots()
        if roots_result and roots_result.roots:
            first_root = roots_result.roots[0]
            path = first_root[7:] if first_root.startswith("file://") else first_root
            
            try:
                os.chdir(path)
                ctx.info(f"Changed working directory to: {path}")
            except OSError as e:
                ctx.error(f"Failed to change directory to {path}: {e}")
    except Exception as e:
        ctx.error(f"Error during initialization: {e}")


if __name__ == "__main__":
    mcp.run()