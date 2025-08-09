# My MCP for Filesystem Access for Claude

## References

[Claude Desktop Extensions](https://www.anthropic.com/engineering/desktop-extensions)

## TL;DR

Only works in local Claude for now.

TODO: dxt package is too big to be added as an extension. Fix this

To test it locally:

1. `uv pip compile pyproject.toml > requirements.txt`
2. `uv run mcp-server --debug`

To run it in Claude, add this to your `claude_config.json` file:

```json
    "ai_distiller": {
      "command": "uv",
      "args": [
        "--directory", "/Users/fperez/dev/ai-distiller-mcp",
        "run",
        "mcp-server"
      ]
    },
```


## Dev

### Requirements

- `pixi`
- `uv`

### Init the dxt

Init dxt project with a manifest

```sh
npx @anthropic-ai/dxt init --yes
```

**Note** When creating the manifest, in the `mpc_config` section, put the full path to the python interpreter ->  `"command": "/Users/fperez/.pyenv/shims/python"`

### Bundle Python libs and Package Project

```sh
pixi install
pixi run bundle
pixi run pack
```

The output `.dxt` file is created on the dxt-package directory. Once the `.dxt` file is created you can drag and drop it to Claude (in the `Settings/Extensions` section.)

### Testing it

Run server with:

```sh
pixi test
```

Then open the inspector:

```sh
DANGEROUSLY_OMIT_AUTH=true npx @modelcontextprotocol/inspector
```

And then:

- go to the URL specified
- select stdio as connection method
- put `pixi` in `Command` input box
- put `run python server/main.py --debug` in the `Arguments` input box
- click connect
- go to tools and list them


**NOTE** For testing the server as extension is run when added to Claude try:

```sh
PYTHONPATH="/Users/fperez/Library/Application Support/Claude/Claude Extensions/local.dxt.francisco-perez-sorrosal.ai-distiler-mcp/server/lib" python /Users/fperez/Library/Application\ Support/Claude/Claude\ Extensions/local.dxt.francisco-perez-sorrosal.ai-distiler-mcp/server/main.py --debug
```
