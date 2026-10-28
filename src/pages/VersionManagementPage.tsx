import { useCallback, useEffect, useState } from 'react';
import { Package, RefreshCw } from 'lucide-react';
import { onCoreInstallProgress } from '../services/events';
import { detectBundledCore, getCoreInstallTask, installBundledCore } from '../services/coreVersions';
import type { BundledCoreInfo, CoreInstallTask } from '../services/coreVersions';
import { getVersion } from '../services/platform';
import { useCoreRuntime } from '../coreRuntime';
import { useI18n } from '../i18n';
import { MessageNotice } from '../appNotice';
import { Notice } from '../components/Notice';

export type { CoreInstallResult, CoreInstallTask, VersionSourceSettings, VersionDownloadSource } from '../services/coreVersions';

export function displayAppVersion(version: string) {
  const resolvedVersion = version.trim();
  return resolvedVersion.startsWith('v') ? resolvedVersion : `v${resolvedVersion}`;
}

export function VersionManagementPage() {
  const { t } = useI18n();
  const { status, refreshStatus } = useCoreRuntime();
  const [appVersion, setAppVersion] = useState('');
  const [bundledCore, setBundledCore] = useState<BundledCoreInfo | null>(null);
  const [task, setTask] = useState<CoreInstallTask | null>(null);
  const [installing, setInstalling] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const refresh = useCallback(async () => {
    setError('');
    try {
      const [version, bundle, installTask] = await Promise.all([
        getVersion(), detectBundledCore(), getCoreInstallTask(),
      ]);
      setAppVersion(version);
      setBundledCore(bundle);
      setTask(installTask);
      await refreshStatus();
    } catch (reason) {
      setError(String(reason));
    }
  }, [refreshStatus]);

  useEffect(() => { void refresh(); }, [refresh]);

  useEffect(() => {
    let disposed = false;
    let stop: (() => void) | undefined;
    void onCoreInstallProgress((event) => {
      if (!disposed) setTask(event.payload);
    }).then((unlisten) => {
      if (disposed) unlisten();
      else stop = unlisten;
    }).catch((reason) => {
      if (!disposed) setError(String(reason));
    });
    return () => { disposed = true; stop?.(); };
  }, []);

  const restore = async () => {
    setInstalling(true);
    setError('');
    setNotice('');
    try {
      const result = await installBundledCore();
      setNotice(t('kernel.install.bundledCompleted', { version: result.version }));
      await refresh();
    } catch (reason) {
      setError(String(reason));
    } finally {
      setInstalling(false);
      await refreshStatus();
    }
  };

  const busy = installing || Boolean(task?.running) || Boolean(status?.starting);
  return (
    <section className="page management-page version-management-page">
      <Notice tone="info">{t('privateBuild.policy')}</Notice>
      <MessageNotice message={error} onDismiss={() => setError('')} />
      <MessageNotice message={notice} tone="success" onDismiss={() => setNotice('')} />
      <section className="surface-bare version-list">
        <div className="version-card-grid">
          <article className="version-list-item app-module-card surface-panel">
            <div className="version-item-content">
              <div className="version-card-top"><h2>{t('privateBuild.name')}</h2></div>
              <dl className="version-metrics-comparison">
                <div className="surface-section surface-muted version-metric-tile">
                  <dt className="version-metric-label">{t('appUpdate.current')}</dt>
                  <dd className="version-metric-value">{appVersion ? displayAppVersion(appVersion) : t('common.detecting')}</dd>
                </div>
              </dl>
            </div>
          </article>
          <article className="version-list-item core-module-card surface-panel">
            <div className="version-item-content">
              <div className="version-card-top"><h2>{t('kernel.versions.coreCardTitle')}</h2></div>
              <dl className="version-metrics-comparison">
                <div className="surface-section surface-muted version-metric-tile">
                  <dt className="version-metric-label">{t('kernel.versions.current')}</dt>
                  <dd className="version-metric-value">{status?.currentVersion || t('kernel.status.notInstalled')}</dd>
                </div>
                <div className="surface-section surface-muted version-metric-tile">
                  <dt className="version-metric-label">{t('privateBuild.bundledCore')}</dt>
                  <dd className="version-metric-value">{bundledCore?.version ?? t('common.unavailable')}</dd>
                </div>
              </dl>
              {busy ? <Notice tone="info" variant="text">{t('kernel.install.inProgress')}</Notice> : null}
              <p>{t('privateBuild.restoreHint')}</p>
            </div>
            <div className="version-card-actions core-actions">
              <button type="button" className="secondary-button" disabled={busy} onClick={() => void refresh()}>
                <RefreshCw size={15} aria-hidden="true" />{t('common.refresh')}
              </button>
              <button type="button" className="primary-button" disabled={busy || !bundledCore} onClick={() => void restore()}>
                <Package size={15} aria-hidden="true" />{t('privateBuild.restore')}
              </button>
            </div>
          </article>
        </div>
      </section>
    </section>
  );
}
