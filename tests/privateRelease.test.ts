import { expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';

test('private build workflow is manual and cannot publish a release', () => {
  const workflow = Bun.YAML.parse(readFileSync('.github/workflows/release.yml','utf8')) as any;
  expect(Object.keys(workflow.on)).toEqual(['workflow_dispatch']);
  expect(workflow.permissions).toEqual({contents:'read'});
  expect(Object.keys(workflow.jobs)).toEqual(['build']);
  expect(workflow.jobs.build.steps.some((step: any) => step.run === 'bash build.sh')).toBe(true);
});
