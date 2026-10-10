import { getLanguage, t } from './core.js'
import { knowledgeGuides } from './knowledgeGuides.js'

export function localizeKnowledgeArticle(article, language = getLanguage()) {
  if (language !== 'uz') return article
  const guide = knowledgeGuides.find((item) => item.sourceTitle === article.title && item.sourceContent === article.content)
  if (!guide) return article
  return {
    ...article,
    title: guide.title,
    summary: article.summary === guide.sourceSummary ? guide.summary : article.summary,
    content: guide.content,
    category: { ...article.category, name: t(article.category.name) },
  }
}
