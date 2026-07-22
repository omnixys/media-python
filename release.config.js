/**
 * @license GPL-3.0-or-later
 * Copyright (C) 2025 Caleb Gyamfi
 * Omnixys Technologies
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
 * See the GNU General Public License for more details.
 *
 * For more information, visit <https://www.gnu.org/licenses/>.
 */

export default {
  branches: ['main'],
  tagFormat: 'v${version}',
  plugins: [
    ['@semantic-release/commit-analyzer', {
      preset: 'conventionalcommits',
      releaseRules: [
        { type: 'breaking', release: 'major' },
        { type: 'feat', release: 'minor' },
        { type: 'fix', release: 'patch' },
        { type: 'perf', release: 'patch' },
        { type: 'refactor', release: 'patch' },
        { type: 'revert', release: 'patch' },
        { type: 'docs', release: false },
        { type: 'style', release: false },
        { type: 'test', release: false },
        { type: 'chore', release: false },
        { type: 'ci', release: false },
        { type: 'build', release: false },
      ],
    }],
    '@semantic-release/release-notes-generator',
    ['@semantic-release/changelog', { changelogFile: 'CHANGELOG.md' }],
    ['@semantic-release/exec', {
      prepareCmd: 'sed -i "s/__version__ = \\".*\\"/__version__ = \\"${nextRelease.version}\\"/" src/omnixys_media/__init__.py',
    }],
    ['@semantic-release/git', {
      assets: ['pyproject.toml', 'CHANGELOG.md', 'src/omnixys_media/__init__.py'],
      message: 'chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}',
    }],
    ['@semantic-release/github', {
      assets: [
        { path: 'CHANGELOG.md', label: 'Changelog' },
        { path: 'dist/**', label: 'Build Artifacts' },
      ],
    }],
  ],
};
