import { describe, expect, it } from 'vitest'
import { parseIntent } from './agent'

describe('agent intent parser', () => {
  it('navigates', () => expect(parseIntent('open watch')).toEqual({ kind: 'navigate', target: 'watch' }))
  it('changes theme', () => expect(parseIntent('switch to light mode')).toEqual({ kind: 'theme', theme: 'light' }))
  it('refuses unsafe automation', () => expect(parseIntent('approve claim automatically').kind).toBe('refuse'))
  it('parses alert ids', () => expect(parseIntent('explain ALT-1001')).toEqual({ kind: 'explain-alert', alertId: 'ALT-1001' }))
  it('parses team assignment', () => expect(parseIntent('assign team 2')).toEqual({ kind: 'assign', team: 'Team 2' }))
  it('parses time scrub', () => expect(parseIntent('scrub to 18:00')).toEqual({ kind: 'scrub', time: 18 }))
})
