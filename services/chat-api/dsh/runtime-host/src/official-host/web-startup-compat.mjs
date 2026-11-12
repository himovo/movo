export const name = 'movo-web-startup-compat'

export function apply(ctx) {
  ctx.provide('webStartup', {
    host: '127.0.0.1',
    port: 0,
    openBrowser: false,
    trustedHosts: [],
  })
}
