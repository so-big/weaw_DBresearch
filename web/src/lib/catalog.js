// Category groups change rarely: load once per page load (admin edits call reset()).
import { get } from './api.js';

let groups;
export function categoryGroups() {
  groups ??= get('/categories').catch((err) => {
    groups = undefined;
    throw err;
  });
  return groups;
}
export function resetCatalog() {
  groups = undefined;
}
