function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical)
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]))
  }
  return value
}

function contract(tool) {
  return {
    name: String(tool.name),
    description: String(tool.description ?? ''),
    schema: canonical(tool.parameters ?? tool.schema ?? tool.inputSchema ?? null),
  }
}

export function modelToolContracts(tools) {
  return tools.map(contract).sort((left, right) => left.name.localeCompare(right.name))
}

export function capabilityToolContracts(tools) {
  return tools.map(contract).sort((left, right) => left.name.localeCompare(right.name))
}
