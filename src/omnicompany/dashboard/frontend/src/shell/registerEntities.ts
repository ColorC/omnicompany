import { registry } from '../entities/registry'
import { workerRegistration } from '../entities/worker'
import { traceRegistration } from '../entities/trace'
import { sessionRegistration } from '../entities/session'
import { noteRegistration } from '../entities/note'
import { planRegistration } from '../entities/plan-folder'
import { settingsRegistration } from '../entities/settings'
import { graphRegistration } from '../entities/graph'
import { teamRegistration, teamBoardRegistration } from '../entities/team'
import { materialRegistration } from '../entities/material'
import { ccSessionRegistration } from '../entities/cc_session'
import { controllerRegistration } from '../entities/controller'
import { materialRegistryRegistration } from '../entities/material_registry'
import { reviewQueueRegistration } from '../entities/review_queue'
import { reviewMaterialRegistration } from '../entities/review_material'
import { webReviewRegistration } from '../entities/web_review'
import { projectRegistration, projectBoardRegistration } from '../entities/project'
import { authoredRegistration } from '../entities/authored'
import { planAuditRegistration } from '../entities/plan_audit'

let registered = false

export function registerAllEntities(): void {
  if (registered) return
  registry.register(projectRegistration)
  registry.register(projectBoardRegistration)
  registry.register(noteRegistration)
  registry.register(graphRegistration)
  registry.register(planRegistration)
  registry.register(workerRegistration)
  registry.register(teamRegistration)
  registry.register(teamBoardRegistration)
  registry.register(materialRegistration)
  registry.register(controllerRegistration)
  registry.register(materialRegistryRegistration)
  registry.register(reviewQueueRegistration)
  registry.register(reviewMaterialRegistration)
  registry.register(webReviewRegistration)
  registry.register(sessionRegistration)
  registry.register(ccSessionRegistration)
  registry.register(traceRegistration)
  registry.register(authoredRegistration)
  registry.register(planAuditRegistration)
  registry.register(settingsRegistration)
  registered = true
}
