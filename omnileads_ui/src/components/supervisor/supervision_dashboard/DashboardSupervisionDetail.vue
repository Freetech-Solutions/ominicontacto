<template>
  <div class="dashboard-shell">
    <div class="dashboard-status-header">
      <div class="dashboard-overview-row">
        <div
          v-for="metric in overviewMetrics"
          :key="metric.label"
          class="dashboard-status-item"
        >
          <span
            class="dashboard-status-dot"
            :style="{ background: metric.color }"
          ></span>
          <span class="dashboard-status-label">{{ metric.label }}</span>
          <strong class="dashboard-status-value">{{ metric.value }}</strong>
        </div>
      </div>

      <div
        class="dashboard-channel-row"
        role="list"
        :aria-label="$t('views.dashboard_home_page.configured_channels')"
      >
        <div
          v-for="metric in resourceMetrics"
          :key="metric.key"
          class="dashboard-channel-item"
          role="listitem"
          tabindex="0"
          :aria-label="`${metric.label}: ${metric.value}`"
          :style="{
            '--channel-color': metric.color,
            '--channel-tint': metric.tint
          }"
        >
          <span class="dashboard-channel-icon-wrap">
            <i
              :class="['dashboard-channel-icon', metric.icon]"
              aria-hidden="true"
            ></i>
          </span>
          <strong class="dashboard-channel-value">{{ metric.value }}</strong>
          <span
            class="dashboard-channel-tooltip"
            role="tooltip"
          >{{ metric.label }}</span>
        </div>
      </div>
    </div>

    <div class="grid dashboard-grid">
      <div
        v-for="(item, index) in reportData.active_campaigns"
        :key="index"
        class="col-12 md:col-6 xl:col-3"
      >
        <CampaingActiveChart
          :chartName="index"
          :chartData="item"
        />
      </div>
    </div>

    <div class="grid dashboard-grid">
      <div class="col-12 xl:col-8">
        <section class="dashboard-panel dashboard-panel-hero">
          <header class="dashboard-panel-header">
            <div>
              <span class="dashboard-panel-kicker">
                {{ $t("views.dashboard_home_page.today") }} / {{ $t("views.dashboard_home_page.yesterday") }}
              </span>
              <h3 class="dashboard-panel-title">
                {{ $t("views.dashboard_home_page.authenticated_agents") }}
              </h3>
            </div>
            <div class="dashboard-panel-emphasis">
              <span class="dashboard-panel-emphasis-label">
                {{ $t("views.dashboard_home_page.today") }}
              </span>
              <strong>{{ currentAuthenticatedAgents }}</strong>
            </div>
          </header>
          <div class="dashboard-chart-wrap dashboard-chart-wrap-hero">
            <StateAgentsChartLine
              :chartLineInterval="chartLineIntervalAuth"
              :chartLineEventYesterdayData="chartLineAuthEventYesterdayData"
              :chartLineEventTodayData="chartLineAuthEventTodayData"
            />
          </div>
        </section>
      </div>

      <div class="col-12 xl:col-4">
        <section class="dashboard-panel dashboard-panel-side">
          <header class="dashboard-panel-header dashboard-panel-header-stacked">
            <div>
              <span class="dashboard-panel-kicker">
                {{ $t("views.dashboard_home_page.call_sumary") }}
              </span>
              <h3 class="dashboard-panel-title">
                {{ totalContactedCalls }}
              </h3>
            </div>
            <span class="dashboard-pill">
              {{ totalActiveCampaigns }}
            </span>
          </header>

          <div class="dashboard-highlight-grid">
            <div class="dashboard-highlight-card">
              <span class="dashboard-highlight-label">
                {{ $t("views.dashboard_home_page.authenticated_agents") }}
              </span>
              <strong>{{ currentAuthenticatedAgents }}</strong>
            </div>
            <div class="dashboard-highlight-card">
              <span class="dashboard-highlight-label">
                {{ $t("views.dashboard_home_page.califications") }}
              </span>
              <strong>{{ currentCalifications }}</strong>
            </div>
          </div>

          <div class="dashboard-breakdown">
            <div class="dashboard-breakdown-group">
              <h4>{{ $t("views.dashboard_home_page.call_sumary") }}</h4>
              <div
                v-for="metric in contactedMetrics"
                :key="metric.label"
                class="dashboard-breakdown-row"
              >
                <div class="dashboard-breakdown-main">
                  <span
                    class="dashboard-breakdown-dot"
                    :style="{ background: metric.color }"
                  ></span>
                  <span>{{ metric.label }}</span>
                </div>
                <strong>{{ metric.value }}</strong>
              </div>
            </div>

            <div class="dashboard-breakdown-group">
              <h4>{{ $t("views.dashboard_home_page.agent_status") }}</h4>
              <div
                v-for="metric in agentStateMetrics"
                :key="metric.label"
                class="dashboard-breakdown-row"
              >
                <div class="dashboard-breakdown-main">
                  <span
                    class="dashboard-breakdown-dot"
                    :style="{ background: metric.color }"
                  ></span>
                  <span>{{ metric.label }}</span>
                </div>
                <strong>{{ metric.value }}</strong>
              </div>
            </div>
          </div>
        </section>
      </div>

      <div class="col-12 xl:col-8">
        <section class="dashboard-panel">
          <header class="dashboard-panel-header">
            <div>
              <span class="dashboard-panel-kicker">
                {{ $t("views.dashboard_home_page.today") }} / {{ $t("views.dashboard_home_page.yesterday") }}
              </span>
              <h3 class="dashboard-panel-title">
                {{ $t("views.dashboard_home_page.califications") }}
              </h3>
            </div>
            <div class="dashboard-panel-emphasis">
              <span class="dashboard-panel-emphasis-label">
                {{ $t("views.dashboard_home_page.today") }}
              </span>
              <strong>{{ currentCalifications }}</strong>
            </div>
          </header>
          <div class="dashboard-chart-wrap">
            <StateAgentsChartLine
              :chartLineInterval="chartLineIntervalCalification"
              :chartLineEventYesterdayData="chartLineCalificationEventYesterdayData"
              :chartLineEventTodayData="chartLineCalificationEventTodayData"
            />
          </div>
        </section>
      </div>

      <div class="col-12 xl:col-4">
        <section class="dashboard-panel">
          <header class="dashboard-panel-header">
            <div>
              <span class="dashboard-panel-kicker">
                {{ $t("views.dashboard_home_page.call_sumary") }}
              </span>
              <h3 class="dashboard-panel-title">
                {{ $t("views.dashboard_home_page.call_sumary") }}
              </h3>
            </div>
          </header>
          <div class="dashboard-chart-wrap dashboard-chart-wrap-donut">
            <ContactedCallsChart :chartData="reportData.contacted_calls" />
          </div>
        </section>
      </div>

      <div class="col-12">
        <section class="dashboard-panel">
          <header class="dashboard-panel-header">
            <div>
              <span class="dashboard-panel-kicker">
                {{ totalAgents }}
              </span>
              <h3 class="dashboard-panel-title">
                {{ $t("views.dashboard_home_page.agent_status") }}
              </h3>
            </div>
          </header>
          <div class="dashboard-chart-wrap dashboard-chart-wrap-bar">
            <StateAgentsChart :chartData="reportData.state_agents" />
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script>
import CampaingActiveChart from '@/components/supervisor/supervision_dashboard/charts/CampaingActiveChart.vue';
import StateAgentsChart from '@/components/supervisor/supervision_dashboard/charts/StateAgentsChart';
import ContactedCallsChart from '@/components/supervisor/supervision_dashboard/charts/ContactedCallsChart';
import StateAgentsChartLine from '@/components/supervisor/supervision_dashboard/charts/StateAgentsChartLine';

export default {
    props: {
        reportData: Object,
        resourceCounts: {
            type: Object,
            default: () => ({
                voiceLines: 0,
                whatsappLines: 0,
                metaMessengerAccounts: 0,
                instagramAccounts: 0,
                emailAccounts: 0
            })
        },
        chartLineIntervalAuth: Object,
        chartLineIntervalCalification: Object,
        chartLineAuthEventYesterdayData: Object,
        chartLineAuthEventTodayData: Object,
        chartLineCalificationEventYesterdayData: Object,
        chartLineCalificationEventTodayData: Object
    },
    components: {
        CampaingActiveChart,
        StateAgentsChart,
        ContactedCallsChart,
        StateAgentsChartLine
    },
    computed: {
        totalActiveCampaigns () {
            return this.sumValues(this.reportData.active_campaigns);
        },
        totalContactedCalls () {
            return this.sumValues(this.reportData.contacted_calls);
        },
        totalAgents () {
            return this.sumValues(this.reportData.state_agents);
        },
        currentAuthenticatedAgents () {
            return this.getLastMetricValue(this.chartLineAuthEventTodayData);
        },
        currentCalifications () {
            return this.getLastMetricValue(this.chartLineCalificationEventTodayData);
        },
        overviewMetrics () {
            return [
                {
                    label: this.$t('views.dashboard_home_page.authenticated_agents'),
                    value: this.currentAuthenticatedAgents,
                    color: '#5da3ff'
                },
                {
                    label: this.$t('views.dashboard_home_page.califications'),
                    value: this.currentCalifications,
                    color: '#ffb54d'
                },
                {
                    label: this.$t('views.dashboard_home_page.call_sumary'),
                    value: this.totalContactedCalls,
                    color: '#8FC641'
                }
            ];
        },
        resourceMetrics () {
            return [
                {
                    key: 'voice',
                    label: this.$t('views.dashboard_home_page.voice_lines'),
                    value: Number(this.resourceCounts?.voiceLines || 0),
                    color: '#0EA5E9',
                    tint: 'rgba(14, 165, 233, 0.13)',
                    icon: 'pi pi-phone'
                },
                {
                    key: 'whatsapp',
                    label: this.$t('views.dashboard_home_page.whatsapp_lines'),
                    value: Number(this.resourceCounts?.whatsappLines || 0),
                    color: '#16A765',
                    tint: 'rgba(22, 167, 101, 0.13)',
                    icon: 'pi pi-whatsapp'
                },
                {
                    key: 'messenger',
                    label: this.$t('views.dashboard_home_page.meta_messenger_accounts'),
                    value: Number(this.resourceCounts?.metaMessengerAccounts || 0),
                    color: '#1877F2',
                    tint: 'rgba(24, 119, 242, 0.13)',
                    icon: 'pi pi-facebook'
                },
                {
                    key: 'instagram',
                    label: this.$t('views.dashboard_home_page.instagram_accounts'),
                    value: Number(this.resourceCounts?.instagramAccounts || 0),
                    color: '#D62976',
                    tint: 'rgba(214, 41, 118, 0.13)',
                    icon: 'pi pi-instagram'
                },
                {
                    key: 'email',
                    label: this.$t('views.dashboard_home_page.email_accounts'),
                    value: Number(this.resourceCounts?.emailAccounts || 0),
                    color: '#6D5DFB',
                    tint: 'rgba(109, 93, 251, 0.13)',
                    icon: 'pi pi-envelope'
                }
            ];
        },
        contactedMetrics () {
            const colors = {
                attended: '#8FC641',
                failed: '#ff7b72'
            };
            return this.getMetricEntries(this.reportData.contacted_calls, 'call_sumary', colors);
        },
        agentStateMetrics () {
            const colors = {
                ready: '#7ce38b',
                oncall: '#5da3ff',
                pause: '#ffb54d'
            };
            return this.getMetricEntries(this.reportData.state_agents, 'agent_status', colors);
        }
    },
    methods: {
        sumValues (data = {}) {
            return Object.values(data || {}).reduce((total, value) => total + Number(value || 0), 0);
        },
        getLastMetricValue (data = []) {
            const validEntries = (data || []).filter(value => value !== null && value !== undefined);
            return validEntries.length ? validEntries[validEntries.length - 1] : 0;
        },
        getMetricEntries (data = {}, translationPrefix = '', colors = {}) {
            return Object.entries(data || {}).map(([key, value]) => {
                const translationKey = `views.dashboard_home_page.${translationPrefix}_${key}`;
                const translatedLabel = this.$t(translationKey);
                return {
                    key,
                    label: translatedLabel !== translationKey ? translatedLabel : this.titleize(key),
                    value: Number(value || 0),
                    color: colors[key] || '#5da3ff'
                };
            });
        },
        titleize (text = '') {
            return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
        }
    }
};
</script>

<style>
.dashboard-shell {
  --dashboard-surface: rgba(255, 255, 255, 0.95);
  --dashboard-surface-strong: #ffffff;
  --dashboard-border: rgba(15, 23, 42, 0.08);
  --dashboard-outline: rgba(15, 23, 42, 0.04);
  --dashboard-text: #162033;
  --dashboard-muted: #6a778b;
  --dashboard-shadow: 0 24px 60px rgba(15, 23, 42, 0.1);
  --dashboard-shell-bg:
    radial-gradient(circle at top left, rgba(93, 163, 255, 0.16), transparent 30%),
    radial-gradient(circle at top right, rgba(143, 198, 65, 0.16), transparent 35%),
    linear-gradient(180deg, #f5f7fb 0%, #edf2f8 100%);
  color: var(--dashboard-text);
  width: 100%;
  max-width: 100%;
  padding: 1rem;
  border-radius: 28px;
  background: var(--dashboard-shell-bg);
  overflow-x: hidden;
  box-sizing: border-box;
}

html.dark-mode .dashboard-shell {
  --dashboard-surface: rgba(18, 22, 33, 0.92);
  --dashboard-surface-strong: #171c28;
  --dashboard-border: rgba(255, 255, 255, 0.08);
  --dashboard-outline: rgba(255, 255, 255, 0.04);
  --dashboard-text: #f5f7fb;
  --dashboard-muted: #9aa8bf;
  --dashboard-shadow: 0 24px 60px rgba(0, 0, 0, 0.35);
  --dashboard-shell-bg:
    radial-gradient(circle at top left, rgba(93, 163, 255, 0.18), transparent 30%),
    radial-gradient(circle at top right, rgba(255, 181, 77, 0.16), transparent 32%),
    linear-gradient(180deg, #0d1118 0%, #121723 100%);
}

.dashboard-grid {
  margin-top: 0;
  margin-right: 0;
  margin-left: 0;
}

.dashboard-status-header {
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
  margin-bottom: 1.5rem;
}

.dashboard-overview-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.dashboard-channel-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.55rem;
  padding-top: 0.8rem;
  border-top: 1px solid var(--dashboard-border);
}

.dashboard-status-item {
  display: inline-flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.9rem 1rem;
  border-radius: 999px;
  background: var(--dashboard-surface);
  border: 1px solid var(--dashboard-border);
  box-shadow: var(--dashboard-shadow);
  backdrop-filter: blur(14px);
}

.dashboard-status-dot {
  width: 0.65rem;
  height: 0.65rem;
  border-radius: 999px;
  box-shadow: 0 0 0 0.3rem rgba(255, 255, 255, 0.08);
}

.dashboard-status-label {
  color: var(--dashboard-muted);
  font-size: 0.92rem;
}

.dashboard-status-value {
  font-size: 1rem;
  color: var(--dashboard-text);
}

.dashboard-channel-item {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.55rem;
  min-width: 4.35rem;
  min-height: 3.25rem;
  padding: 0.42rem 0.65rem 0.42rem 0.45rem;
  border-radius: 18px;
  background: var(--dashboard-surface);
  border: 1px solid var(--dashboard-border);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.07);
  cursor: help;
  outline: none;
  transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
}

.dashboard-channel-item:hover,
.dashboard-channel-item:focus-visible {
  z-index: 5;
  transform: translateY(-2px);
  border-color: var(--channel-color);
  box-shadow: 0 14px 30px rgba(15, 23, 42, 0.12);
}

.dashboard-channel-item:focus-visible {
  box-shadow: 0 0 0 3px var(--channel-tint), 0 14px 30px rgba(15, 23, 42, 0.12);
}

.dashboard-channel-icon-wrap {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.15rem;
  height: 2.15rem;
  flex: 0 0 2.15rem;
  border-radius: 12px;
  color: var(--channel-color);
  background: var(--channel-tint);
}

.dashboard-channel-icon {
  font-size: 1.05rem;
}

.dashboard-channel-value {
  min-width: 1ch;
  color: var(--dashboard-text);
  font-size: 1.05rem;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.dashboard-channel-tooltip {
  position: absolute;
  top: calc(100% + 0.55rem);
  left: 50%;
  z-index: 10;
  width: max-content;
  max-width: 15rem;
  padding: 0.45rem 0.65rem;
  border-radius: 9px;
  color: #ffffff;
  background: #162033;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.18);
  font-size: 0.78rem;
  font-weight: 600;
  line-height: 1.25;
  text-align: center;
  pointer-events: none;
  opacity: 0;
  transform: translate(-50%, -0.25rem);
  transition: opacity 140ms ease, transform 140ms ease;
}

.dashboard-channel-item:last-child .dashboard-channel-tooltip {
  right: 0;
  left: auto;
  transform: translateY(-0.25rem);
}

.dashboard-channel-item:hover .dashboard-channel-tooltip,
.dashboard-channel-item:focus-visible .dashboard-channel-tooltip {
  opacity: 1;
  transform: translate(-50%, 0);
}

.dashboard-channel-item:last-child:hover .dashboard-channel-tooltip,
.dashboard-channel-item:last-child:focus-visible .dashboard-channel-tooltip {
  transform: translateY(0);
}

html.dark-mode .dashboard-channel-item {
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.22);
}

html.dark-mode .dashboard-channel-tooltip {
  color: #162033;
  background: #f5f7fb;
}

@media (max-width: 640px) {
  .dashboard-overview-row,
  .dashboard-channel-row {
    justify-content: flex-start;
  }

  .dashboard-status-item {
    flex: 1 1 auto;
  }

  .dashboard-channel-item {
    min-width: 4rem;
  }
}

.dashboard-panel {
  position: relative;
  height: 100%;
  padding: 1.15rem;
  border-radius: 26px;
  background: var(--dashboard-surface);
  border: 1px solid var(--dashboard-border);
  box-shadow: var(--dashboard-shadow);
  overflow: hidden;
}

.dashboard-panel::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  padding: 1px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.24), transparent 40%);
  -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
}

.dashboard-panel-hero {
  min-height: 24rem;
}

.dashboard-panel-side {
  min-height: 24rem;
}

.dashboard-panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.25rem;
}

.dashboard-panel-header-stacked {
  align-items: center;
}

.dashboard-panel-kicker {
  display: inline-block;
  margin-bottom: 0.4rem;
  color: var(--dashboard-muted);
  font-size: 0.82rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.dashboard-panel-title {
  margin: 0;
  font-size: 1.4rem;
  line-height: 1.2;
  color: var(--dashboard-text);
}

.dashboard-panel-emphasis {
  min-width: 5.5rem;
  padding: 0.85rem 1rem;
  border-radius: 18px;
  text-align: right;
  background: rgba(93, 163, 255, 0.12);
  border: 1px solid rgba(93, 163, 255, 0.18);
}

html.dark-mode .dashboard-panel-emphasis {
  background: rgba(93, 163, 255, 0.14);
}

.dashboard-panel-emphasis-label {
  display: block;
  margin-bottom: 0.3rem;
  color: var(--dashboard-muted);
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.dashboard-panel-emphasis strong {
  font-size: 1.5rem;
  color: var(--dashboard-text);
}

.dashboard-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 3rem;
  height: 3rem;
  padding: 0 0.9rem;
  border-radius: 999px;
  font-weight: 700;
  color: var(--dashboard-text);
  background: rgba(143, 198, 65, 0.16);
  border: 1px solid rgba(143, 198, 65, 0.2);
}

.dashboard-highlight-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.9rem;
  margin-bottom: 1.35rem;
}

.dashboard-highlight-card {
  padding: 1rem;
  border-radius: 20px;
  background: var(--dashboard-surface-strong);
  border: 1px solid var(--dashboard-outline);
}

html.dark-mode .dashboard-highlight-card {
  background: rgba(255, 255, 255, 0.03);
}

.dashboard-highlight-label {
  display: block;
  margin-bottom: 0.55rem;
  color: var(--dashboard-muted);
  font-size: 0.9rem;
}

.dashboard-highlight-card strong {
  font-size: 1.85rem;
  color: var(--dashboard-text);
}

.dashboard-breakdown {
  display: grid;
  gap: 1rem;
}

.dashboard-breakdown-group {
  padding: 1rem;
  border-radius: 20px;
  background: var(--dashboard-surface-strong);
  border: 1px solid var(--dashboard-outline);
}

html.dark-mode .dashboard-breakdown-group {
  background: rgba(255, 255, 255, 0.03);
}

.dashboard-breakdown-group h4 {
  margin: 0 0 0.85rem;
  color: var(--dashboard-text);
  font-size: 0.96rem;
}

.dashboard-breakdown-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.65rem 0;
  border-top: 1px solid var(--dashboard-border);
}

.dashboard-breakdown-row:first-of-type {
  border-top: 0;
  padding-top: 0;
}

.dashboard-breakdown-main {
  display: inline-flex;
  align-items: center;
  gap: 0.65rem;
  color: var(--dashboard-muted);
}

.dashboard-breakdown-row strong {
  color: var(--dashboard-text);
}

.dashboard-breakdown-dot {
  width: 0.7rem;
  height: 0.7rem;
  border-radius: 999px;
}

.dashboard-chart-wrap {
  height: 17rem;
}

.dashboard-chart-wrap-hero {
  height: 17.5rem;
}

.dashboard-chart-wrap-donut {
  height: 16rem;
}

.dashboard-chart-wrap-bar {
  height: 16rem;
}

@media screen and (max-width: 991px) {
  .dashboard-shell {
    padding: 0.85rem;
    border-radius: 20px;
  }

  .dashboard-panel,
  .dashboard-panel-hero,
  .dashboard-panel-side {
    min-height: auto;
  }

  .dashboard-highlight-grid {
    grid-template-columns: 1fr;
  }

  .dashboard-panel-header {
    flex-direction: column;
  }

  .dashboard-panel-emphasis {
    width: 100%;
    text-align: left;
  }

  .dashboard-chart-wrap,
  .dashboard-chart-wrap-hero,
  .dashboard-chart-wrap-donut,
  .dashboard-chart-wrap-bar {
    height: 17rem;
  }
}
</style>
