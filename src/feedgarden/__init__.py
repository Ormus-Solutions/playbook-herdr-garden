"""The parts of the Garden: a curated feed your agents can act on.

The tool is a pipeline, one module per stage:

    sources  -> read RSS, Atom and GitHub search results into items
    kinds    -> sort each item into a kind and keep or skip it (the filter)
    render   -> draw the board as text (the preview, and the pane's rows)
    pane     -> the browsable pane, with one key per action
    handoff  -> build the prompt for the selected item and hand it to an agent
    herdr_tab-> the Herdr commands that put the pane and the agent in one tab

Each stage takes data in and gives data out, so each one is tested alone.
"""
