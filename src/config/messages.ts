export const dataViewMessages = {
  approvals: {
    initial: {
      description:
        'The review queue could not be loaded. Try again when you are ready.',
      title: 'Review is unavailable',
    },
    refresh:
      'The queue could not be refreshed. The last loaded items remain visible.',
  },
  entries: {
    initial: {
      description:
        'Your entries could not be loaded. Try again when you are ready.',
      title: 'Entries are unavailable',
    },
    refresh:
      'Entries could not be refreshed. The last loaded entries remain visible.',
  },
  entryDetail: {
    initial: {
      description:
        'This entry could not be loaded. Try again when you are ready.',
      title: 'Entry unavailable',
    },
    refresh:
      'This entry could not be refreshed. The last loaded version remains visible.',
  },
  journey: {
    initial: {
      description:
        'Orion could not assemble your journey history. Your original entries are unchanged.',
      title: 'Your journey is unavailable',
    },
    refresh:
      'New journey data could not be loaded. Showing the last available view.',
  },
  profile: {
    initial: {
      description: 'Orion could not load your profile settings.',
      title: 'Profile settings are unavailable',
    },
    refresh:
      'Profile settings could not be refreshed. The last loaded settings remain visible.',
  },
  reflections: {
    initial: {
      description:
        'Orion could not gather your reflection history. Try again when you are ready.',
      title: 'Reflections are unavailable',
    },
    refresh:
      'New reflection data could not be loaded. Showing the last available view.',
  },
} as const;

export function savedItemsDataViewMessages(title: string) {
  return {
    initial: {
      description: `${title} could not be loaded. Try again when you are ready.`,
      title: `${title} are unavailable`,
    },
    refresh: `${title} could not be refreshed. The last loaded items remain visible.`,
  };
}
