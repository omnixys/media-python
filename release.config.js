const package_name = process.env.PACKAGE_NAME;

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
    ['@semantic-release/release-notes-generator', {
      preset: 'conventionalcommits',
      writerOpts: {
        commitsSort: ['subject', 'scope'],
        headerFormat: '## What\'s Changed\n\n',
        transform: (commit, context) => {
          const issues = [];
          let subject = commit.subject || '';

          subject = subject.replace(/@(\w+)/g, '**@$1**');

          subject = subject.replace(/#(\d+)/g, (match, issue) => {
            issues.push(issue);
            return match;
          });

          const scope = commit.scope ? `**${commit.scope}:** ` : '';

          return {
            subject: `${scope}${subject}`,
            type: commit.type,
            scope: commit.scope,
            hash: commit.hash ? commit.hash.substring(0, 7) : undefined,
            references: issues.map(issue => ({
              issue,
              prefix: '#',
              raw: `#${issue}`,
            })),
          };
        },
      },
      presetConfig: {
        types: [
          { type: 'feat', section: '🚀 Features' },
          { type: 'fix', section: '🐛 Bug Fixes' },
          { type: 'perf', section: '⚡ Performance Improvements' },
          { type: 'refactor', section: '♻️ Refactoring' },
          { type: 'revert', section: '⏪ Reverts' },
        ],
      },
    }],
    ['@semantic-release/changelog', {
      changelogFile: 'CHANGELOG.md',
      changelogTitle: '# Changelog\n\nAll notable changes in this project will be documented in this file.\n',
    }],
    ['@semantic-release/exec', {
      prepareCmd: 'sed -i "s/__version__ = \\".*\\"/__version__ = \\"${nextRelease.version}\\"/" src/omnixys_*/__init__.py',
    }],
    ['@semantic-release/git', {
      assets: ['pyproject.toml', `src/${package_name.replace(/-/g, '_')}/__init__.py`, 'CHANGELOG.md'],
      message: 'chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}',
    }],
    ['@semantic-release/github', {
      assets: [
        { path: 'CHANGELOG.md', label: 'Changelog' },
      ],
      releaseBodyTemplate: '## ${nextRelease.version}\n\n' +
        '📅 **Date:** ' + new Date().toISOString().split('T')[0] + '\n' +
        '🌿 **Branch:** main\n' +
        '🔖 **Tag:** `${nextRelease.tag}`\n' +
        '📦 **Package:** ' + package_name + '\n\n' +
        '---\n\n' +
        '${nextRelease.notes}\n\n' +
        '---\n\n' +
        '## Installation\n\n' +
        '```bash\n' +
        'pip install ' + package_name + '==${nextRelease.version}\n' +
        '```\n\n' +
        '## Links\n\n' +
        '- [GitHub Repository](https://github.com/omnixys/' + package_name + ')\n' +
        '- [Documentation](https://omnixys.github.io/omnixys)\n',
    }],
  ],
};
