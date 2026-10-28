import { Notice } from '../components/Notice';
import { useI18n } from '../i18n';

export function PluginsPage() {
  const { t } = useI18n();
  return <section className="page management-page">
    <Notice tone="info">{t('privateBuild.pluginsDisabled')}</Notice>
  </section>;
}
