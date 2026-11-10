/**
 * useIdentity — U1 hook.
 *
 * Loads the current actor's identity from GET /identity/me and exposes
 * helpers to switch the tenant and persona.  Switching re-fetches identity
 * immediately and notifies the rest of the app via a storage event so that
 * polling hooks (useNow, etc.) can re-initialise.
 */
import { useState, useEffect, useCallback } from 'react'
import {
  getIdentityMe, getPersonas,
  setDemoTenant, setDemoActor, getDemoTenant, getDemoActor,
  type IdentityMe, type PersonaInfo,
} from '../api/client'

export interface IdentityState {
  me: IdentityMe | null
  personas: PersonaInfo[]
  currentTenant: string
  currentActor: string
  loading: boolean
  switchTenant: (id: string) => void
  switchActor: (id: string) => void
}

export function useIdentity(): IdentityState {
  const [me, setMe] = useState<IdentityMe | null>(null)
  const [personas, setPersonas] = useState<PersonaInfo[]>([])
  const [currentTenant, setCurrentTenant] = useState(getDemoTenant())
  const [currentActor,  setCurrentActor]  = useState(getDemoActor())
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [identity, plist] = await Promise.all([getIdentityMe(), getPersonas()])
      setMe(identity)
      setPersonas(plist)
    } catch {
      // Non-fatal: leave stale state
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const switchTenant = useCallback((id: string) => {
    setDemoTenant(id)
    setCurrentTenant(id)
    // Reset actor to default for the new tenant
    setDemoActor('student_alex')
    setCurrentActor('student_alex')
    load()
  }, [load])

  const switchActor = useCallback((id: string) => {
    setDemoActor(id)
    setCurrentActor(id)
    load()
  }, [load])

  return { me, personas, currentTenant, currentActor, loading, switchTenant, switchActor }
}
