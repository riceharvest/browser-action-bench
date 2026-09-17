"""Hermes registration snippet for the neeble_browser tool.

Import this from a Hermes plugin/tool module. It deliberately exposes one
high-level tool: the supervising model supplies the current compact state and
legal action schemas, while Neeble chooses one action and the persistent
executor verifies it.
"""
from integrations.hermes_neeble import neeble_browser

NEEBLE_TOOL_SCHEMA = {
    'name': 'neeble',
    'description': 'Fast local browser action layer. Give a goal, compact current browser state, and legal browser actions. Returns one verified action or an escalation request.',
    'parameters': {
        'type': 'object',
        'properties': {
            'goal': {'type': 'string'},
            'state': {'type': 'object'},
            'tools': {'type': 'array', 'items': {'type': 'object'}},
        },
        'required': ['goal', 'state', 'tools'],
        'additionalProperties': False,
    },
}

def register(registry):
    registry.register(
        name='neeble',
        toolset='browser',
        schema=NEEBLE_TOOL_SCHEMA,
        handler=lambda args, **_: neeble_browser(args['goal'], args['state'], args['tools']),
    )
