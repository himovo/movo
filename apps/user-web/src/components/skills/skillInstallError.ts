import { t } from '../../composables/i18n';

type ErrorDetail = { code?: string; file?: string; field?: string };

const MESSAGE_KEYS: Record<string, string> = {
  zip_required: 'skills.install_zip_required',
  unsafe_archive_path: 'skills.install_error.unsafe_archive_path',
  missing_frontmatter: 'skills.install_error.missing_frontmatter',
  invalid_frontmatter: 'skills.install_error.invalid_frontmatter',
  invalid_invocation_policy: 'skills.install_error.invalid_invocation_policy',
  empty_archive: 'skills.install_error.empty_archive',
  archive_too_large: 'skills.install_error.archive_too_large',
  invalid_zip: 'skills.install_error.invalid_zip',
  symlink_not_allowed: 'skills.install_error.symlink_not_allowed',
  encrypted_archive: 'skills.install_error.encrypted_archive',
  duplicate_archive_path: 'skills.install_error.duplicate_archive_path',
  file_too_large: 'skills.install_error.file_too_large',
  suspicious_compression: 'skills.install_error.suspicious_compression',
  too_many_files: 'skills.install_error.too_many_files',
  expanded_archive_too_large: 'skills.install_error.expanded_archive_too_large',
  missing_skill_md: 'skills.install_error.missing_skill_md',
  multiple_skills: 'skills.install_error.multiple_skills',
  invalid_bundle_structure: 'skills.install_error.invalid_bundle_structure',
  skill_md_not_utf8: 'skills.install_error.skill_md_not_utf8',
  invalid_skill_name: 'skills.install_error.invalid_skill_name',
  empty_skill_body: 'skills.install_error.empty_skill_body',
  invalid_market_metadata: 'skills.install_error.invalid_market_metadata',
  invalid_version: 'skills.install_error.invalid_version',
  invalid_tools: 'skills.install_error.invalid_tools',
  organization_install_forbidden: 'skills.install_error.organization_install_forbidden',
  missing_expert_manifest: 'skills.install_error.missing_expert_manifest',
  invalid_expert_manifest: 'skills.install_error.invalid_expert_manifest',
  missing_expert_descriptor: 'skills.install_error.missing_expert_descriptor',
  missing_expert_children: 'skills.install_error.missing_expert_children',
  expert_children_mismatch: 'skills.install_error.expert_children_mismatch',
  missing_expert_child: 'skills.install_error.missing_expert_child',
  expert_descriptor_name_mismatch: 'skills.install_error.expert_descriptor_name_mismatch',
  expert_instructions_too_large: 'skills.install_error.expert_instructions_too_large',
};

function messageKey(detail: ErrorDetail): string {
  if (detail.code === 'metadata_mismatch') {
    return detail.field === 'version'
      ? 'skills.install_error.version_mismatch'
      : 'skills.install_error.slug_mismatch';
  }
  if (detail.code === 'missing_metadata') {
    return detail.field === 'description'
      ? 'skills.install_error.missing_description'
      : 'skills.install_error.missing_name';
  }
  return MESSAGE_KEYS[detail.code || ''] || 'skills.install_error.invalid_package';
}

export function localizeSkillInstallError(error: any): { title: string; message: string } {
  const detail = error?.response?.data?.detail;
  const structuredFailure = detail && typeof detail === 'object' && !Array.isArray(detail);
  if (!structuredFailure) {
    return { title: t('skills.install_failed'), message: t('skills.install_error.request_failed') };
  }
  const context = [
    detail.file ? t('skills.install_error.file', { file: detail.file }) : '',
    detail.field ? t('skills.install_error.field', { field: detail.field }) : '',
  ].filter(Boolean);
  return {
    title: error?.response?.status === 400 ? t('skills.install_validation_failed') : t('skills.install_failed'),
    message: [t(messageKey(detail)), ...context].join(' · '),
  };
}

export function localizeSkillInstallWarning(warning: {
  code: string; message: string; tool?: string; packageVersion?: string; skillVersion?: string;
  childSlug?: string; declaredName?: string; skillName?: string;
}): string {
  if (warning.code === 'version_metadata_mismatch') {
    return t('skills.install_warning.version_mismatch', {
      packageVersion: warning.packageVersion || '',
      skillVersion: warning.skillVersion || '',
    });
  }
  if (warning.code === 'undeclared_tool_reference') {
    return t('skills.install_warning.undeclared_tool', { tool: warning.tool || '' });
  }
  if (warning.code === 'expert_child_name_mismatch') {
    return t('skills.install_warning.expert_child_name_mismatch', {
      childSlug: warning.childSlug || '', skillName: warning.skillName || '',
    });
  }
  return t('skills.install_warning.generic');
}
