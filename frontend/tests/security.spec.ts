import { test, expect } from '@playwright/test';
import { randomBytes } from 'node:crypto';

// Run via scripts/test-security.py: never rotate the developer's real password.
test('change password through Settings and sign in again', async ({ page }) => {
  test.skip(!process.env.SECURITY_TEST_PASSWORD, 'Requires the disposable security test server.');
  const initialPassword = process.env.SECURITY_TEST_PASSWORD!;
  const replacement = randomBytes(24).toString('base64url');
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await page.getByLabel('Username', { exact: true }).fill('admin');
  await page.getByLabel('Password', { exact: true }).fill(initialPassword);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.getByRole('link', { name: 'Settings', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Account security' })).toBeVisible();
  await page.getByLabel('Current password', { exact: true }).fill(initialPassword);
  await page.getByLabel('New password', { exact: true }).fill(replacement);
  await page.getByLabel('Confirm new password', { exact: true }).fill(replacement + 'mismatch');
  await page.getByRole('button', { name: 'Change password', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText('The new passwords do not match.');
  await page.getByLabel('Confirm new password', { exact: true }).fill(replacement);
  await page.getByLabel('Current password', { exact: true }).fill('incorrect-password');
  await page.getByRole('button', { name: 'Change password', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText('Current password is incorrect.');
  await page.getByLabel('Current password', { exact: true }).fill(initialPassword);
  await page.getByRole('button', { name: 'Change password', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Welcome to your workspace' })).toBeVisible();
  await expect(page.getByRole('status')).toHaveText('Password changed. Sign in with your new password.');
  await page.getByLabel('Password', { exact: true }).fill(replacement);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Infrastructure overview' })).toBeVisible();
  expect(errors).toEqual([]);
});
