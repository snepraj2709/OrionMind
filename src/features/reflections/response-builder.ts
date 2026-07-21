/** Test-only aggregate response builder. Production paths must not import it. */
import type {
  EvidenceItem,
  ReflectionApiResponse,
  ReflectionRange,
} from './api-schema';
import { reflectionApiFixture } from './fixtures';

export interface BuildReflectionResponseInput {
  range?: ReflectionRange;
  evidence?: EvidenceItem[];
}

export function buildReflectionApiResponse({
  evidence,
  range = 'all',
}: BuildReflectionResponseInput = {}): ReflectionApiResponse {
  const fixture = structuredClone(reflectionApiFixture);
  fixture.range = range;
  if (evidence && fixture.data.hiddenDriver.status === 'available') {
    fixture.data.hiddenDriver.evidence = evidence;
  }
  return fixture;
}
