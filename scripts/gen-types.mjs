// Usage: node scripts/gen-types.mjs > web/src/api/generated.ts
// Requires a running server: onestop serve
import { execSync } from 'child_process'

execSync(
  'npx openapi-typescript http://localhost:8000/openapi.json -o web/src/api/generated.ts',
  { stdio: 'inherit' },
)
