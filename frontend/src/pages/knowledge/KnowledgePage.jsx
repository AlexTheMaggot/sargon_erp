import { formatLongDate, getLocale, t } from '../../i18n/core'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { ListControls } from '../../components/ListControls/ListControls'
import { Modal } from '../../components/Modal/Modal'
import { emptyKnowledgeArticleForm, emptyKnowledgeCategoryForm } from '../../constants/forms'
import { useKnowledgeBase } from '../../hooks/useKnowledgeBase'
import { useListControls } from '../../hooks/useListControls'
import { localizeKnowledgeArticle } from '../../i18n/knowledge'
import './KnowledgePage.css'

function readingMinutes(content) {
  return Math.max(1, Math.ceil(content.trim().split(/\s+/).length / 150))
}

function ArticleContent({ content }) {
  return (
    <div className="knowledge-content">
      {content.split(/\n\s*\n/).map((block, index) => {
        if (block.startsWith('## ')) return <h2 key={index}>{block.slice(3)}</h2>
        if (block.startsWith('### ')) return <h3 key={index}>{block.slice(4)}</h3>
        const lines = block.split('\n')
        if (lines.every((line) => /^\d+\.\s/.test(line))) {
          return <ol key={index}>{lines.map((line, lineIndex) => <li key={lineIndex}>{line.replace(/^\d+\.\s/, '')}</li>)}</ol>
        }
        if (lines.every((line) => line.startsWith('- '))) {
          return <ul key={index}>{lines.map((line, lineIndex) => <li key={lineIndex}>{line.slice(2)}</li>)}</ul>
        }
        return <p key={index}>{block}</p>
      })}
    </div>
  )
}

export function KnowledgePage({ onLogout, token, user }) {
  const { articles, categories, isLoading, isSaving, error, clearError, saveEntity, deleteEntity } = useKnowledgeBase(token)
  const [searchParams, setSearchParams] = useSearchParams()
  const [categoryId, setCategoryId] = useState('')
  const [articleForm, setArticleForm] = useState(null)
  const [isCategoriesOpen, setIsCategoriesOpen] = useState(false)
  const [categoryForm, setCategoryForm] = useState(emptyKnowledgeCategoryForm)
  const [deleteTargetId, setDeleteTargetId] = useState(null)
  const [categoryDeleteId, setCategoryDeleteId] = useState(null)
  const permissions = user?.access?.['knowledge-base'] || []
  const canCreate = user?.is_admin || permissions.includes('create')
  const canUpdate = user?.is_admin || permissions.includes('update')
  const canDelete = user?.is_admin || permissions.includes('delete')
  const localizedArticles = articles.map((article) => localizeKnowledgeArticle(article))
  const sortedCategories = [...categories].sort((first, second) => t(first.name).localeCompare(t(second.name), getLocale()))
  const visibleArticles = localizedArticles
    .filter((article) => !categoryId || String(article.category_id) === categoryId)
    .sort((first, second) => first.title.localeCompare(second.title, getLocale()))
  const controls = useListControls(visibleArticles, (article) => [article.title, article.summary, article.content, t(article.category.name)].join(' '))
  const selectedArticleId = searchParams.get('article')
  const selectedArticle = localizedArticles.find((article) => String(article.id) === selectedArticleId)
  const deleteTarget = localizedArticles.find((article) => article.id === deleteTargetId)
  const selectedCategory = categories.find((category) => String(category.id) === categoryId)

  function selectCategory(id) {
    setCategoryId(id)
    controls.setCurrentPage(1)
    setSearchParams({})
  }

  function editArticle(article = null) {
    clearError()
    article = article ? articles.find((item) => item.id === article.id) : null
    setArticleForm(article
      ? { id: article.id, title: article.title, category_id: article.category_id, summary: article.summary, content: article.content }
      : { ...emptyKnowledgeArticleForm, category_id: categoryId || categories[0]?.id || '' })
  }

  async function submitArticle(event) {
    event.preventDefault()
    const saved = await saveEntity('articles', articleForm)
    if (saved) {
      setArticleForm(null)
      setSearchParams({ article: String(saved.id) })
    }
  }

  async function submitCategory(event) {
    event.preventDefault()
    if (await saveEntity('categories', categoryForm)) setCategoryForm(emptyKnowledgeCategoryForm)
  }

  async function removeArticle() {
    if (await deleteEntity('articles', deleteTarget.id)) {
      if (String(deleteTarget.id) === selectedArticleId) setSearchParams({})
      setDeleteTargetId(null)
    }
  }

  async function removeCategory(id) {
    if (await deleteEntity('categories', id)) {
      setCategoryDeleteId(null)
      if (categoryId === String(id)) setCategoryId('')
      if (categoryForm.id === id) setCategoryForm(emptyKnowledgeCategoryForm)
    }
  }

  return (
    <DashboardShell title={t('База знаний')} onLogout={onLogout} user={user}>
      <section className="knowledge-hero">
        <div>
          <p className="knowledge-eyebrow">{t('SHENOLL / РУКОВОДСТВО ПО СИСТЕМЕ')}</p>
          <h1>{t('База знаний')}</h1>
          <p>{t('Инструкции, ответы и порядок действий — всё для работы с системой в одном месте.')}</p>
        </div>
        <div className="knowledge-hero-meta"><strong>{articles.length}</strong><span>{t('статей в ')}{categories.length}{t(' разделах')}</span></div>
      </section>

      {error && !articleForm && !isCategoriesOpen && !deleteTarget && <p className="access-error" role="alert">{t(error)}</p>}
      <section className="knowledge-layout">
        <aside className="knowledge-sidebar" aria-label={t('Разделы базы знаний')}>
          <h2>{t('Разделы')}</h2>
          <button className={`knowledge-category ${!categoryId ? 'selected' : ''}`} type="button" aria-pressed={!categoryId} onClick={() => selectCategory('')}><span>{t('Все статьи')}</span><span className="knowledge-count">{articles.length}</span></button>
          {sortedCategories.map((category) => (
            <button className={`knowledge-category ${categoryId === String(category.id) ? 'selected' : ''}`} key={category.id} type="button" aria-pressed={categoryId === String(category.id)} onClick={() => selectCategory(String(category.id))}>
              <span>{t(category.name)}</span><span className="knowledge-count">{articles.filter((article) => article.category_id === category.id).length}</span>
            </button>
          ))}
          {(canCreate || canUpdate || canDelete) && <button className="secondary-button knowledge-manage" type="button" onClick={() => { clearError(); setIsCategoriesOpen(true) }}>{t('Управление разделами')}</button>}
          <p className="knowledge-sidebar-note">{t('Не нашли ответ? Администратор может дополнить инструкции для вашей команды.')}</p>
        </aside>

        <div className="knowledge-main">
          {isLoading ? <div className="access-card"><p className="empty-state" role="status">{t('Загрузка базы знаний…')}</p></div> : selectedArticleId ? (
            selectedArticle ? (
              <article className="knowledge-reader">
                <div className="knowledge-reader-toolbar">
                  <Link className="knowledge-back" to="/knowledge">{t('← К списку статей')}</Link>
                  <div className="row-actions">
                    {canUpdate && <button className="secondary-button" type="button" onClick={() => editArticle(selectedArticle)}>{t('Изменить')}</button>}
                    {canDelete && <button className="danger-button" type="button" onClick={() => { clearError(); setDeleteTargetId(selectedArticle.id) }}>{t('Удалить')}</button>}
                  </div>
                </div>
                <span className="knowledge-tag">{t(selectedArticle.category.name)}</span>
                <h2 className="knowledge-article-title">{selectedArticle.title}</h2>
                {selectedArticle.summary && <p className="knowledge-article-summary">{selectedArticle.summary}</p>}
                <p className="knowledge-date">{t('Обновлено ')}{formatLongDate(selectedArticle.updated_at)} · {readingMinutes(selectedArticle.content)}{t(' мин чтения')}{selectedArticle.updated_by ? ` · ${selectedArticle.updated_by}` : ''}</p>
                <ArticleContent content={selectedArticle.content} />
              </article>
            ) : <div className="access-card"><h2>{t('Статья не найдена')}</h2><p>{t('Возможно, её удалили или ссылка неверна.')}</p><Link to="/knowledge">{t('Вернуться к списку статей')}</Link></div>
          ) : (
            <>
              <div className="knowledge-list-heading">
                <div><h2>{t(selectedCategory?.name) || t('Все статьи')}</h2><p>{t(selectedCategory?.description) || t('Выберите инструкцию или воспользуйтесь поиском по содержимому.')}</p></div>
                {canCreate && <button disabled={!categories.length} type="button" onClick={() => editArticle()}>{t('Добавить статью')}</button>}
              </div>
              <div className="knowledge-search"><ListControls {...controls} searchPlaceholder={t('Поиск по статьям')} onPageChange={controls.setCurrentPage} onSearchChange={controls.setSearchQuery} /></div>
              <div className="knowledge-articles">
                {controls.paginatedItems.map((article) => (
                  <Link className="knowledge-article-card" key={article.id} to={`/knowledge?article=${article.id}`}>
                    <span className="knowledge-tag">{t(article.category.name)}</span>
                    <h3>{article.title}</h3>
                    <p>{article.summary || article.content.slice(0, 160)}</p>
                    <div className="knowledge-card-footer"><span>{readingMinutes(article.content)}{t(' мин чтения')}</span><span>{t('Открыть →')}</span></div>
                  </Link>
                ))}
              </div>
              {!controls.filteredCount && <div className="access-card knowledge-empty"><h3>{controls.searchQuery ? t('Ничего не найдено') : t('В этом разделе пока нет статей')}</h3><p>{controls.searchQuery ? t('Попробуйте другое слово или выберите все разделы.') : t('Добавьте первую инструкцию или выберите другой раздел.')}</p></div>}
            </>
          )}
        </div>
      </section>

      {articleForm && (
        <Modal title={articleForm.id ? t('Редактировать статью') : t('Новая статья')} onClose={() => { if (!isSaving) setArticleForm(null) }}>
          <form className="crud-form knowledge-form" onSubmit={submitArticle}>
            {error && <p className="form-error" role="alert">{t(error)}</p>}
            <label><span>{t('Заголовок')}</span><input disabled={isSaving} maxLength={200} required value={articleForm.title} onChange={(event) => setArticleForm({ ...articleForm, title: event.target.value })} /></label>
            <label><span>{t('Раздел')}</span><select disabled={isSaving} required value={articleForm.category_id} onChange={(event) => setArticleForm({ ...articleForm, category_id: Number(event.target.value) || '' })}><option value="">{t('Выберите раздел')}</option>{sortedCategories.map((category) => <option key={category.id} value={category.id}>{t(category.name)}</option>)}</select></label>
            <label><span>{t('Краткое описание')}</span><textarea disabled={isSaving} maxLength={500} rows={2} value={articleForm.summary} onChange={(event) => setArticleForm({ ...articleForm, summary: event.target.value })} /></label>
            <label><span>{t('Текст статьи')}</span><textarea className="knowledge-content-input" disabled={isSaving} maxLength={100000} required rows={12} value={articleForm.content} onChange={(event) => setArticleForm({ ...articleForm, content: event.target.value })} /></label>
            <p className="knowledge-editor-hint">{t('Разделяйте абзацы пустой строкой. Заголовки начинайте с «## », пункты списка — с «- » или «1. ».')}</p>
            <p className="knowledge-editor-hint">{t('Редактируется исходный текст. Пользовательские статьи автоматически не переводятся.')}</p>
            <div className="form-actions"><button disabled={isSaving} type="submit">{isSaving ? t('Сохраняем…') : t('Сохранить статью')}</button><button className="secondary-button" disabled={isSaving} type="button" onClick={() => setArticleForm(null)}>{t('Отмена')}</button></div>
          </form>
        </Modal>
      )}

      {isCategoriesOpen && (
        <Modal title={t('Разделы базы знаний')} onClose={() => { if (!isSaving) setIsCategoriesOpen(false) }}>
          <div className="knowledge-section-manager">
            {error && <p className="form-error" role="alert">{t(error)}</p>}
            <div className="knowledge-section-list">
              {sortedCategories.map((category) => (
                <div className="knowledge-section-row" key={category.id}>
                  <strong>{t(category.name)}</strong>
                  {categoryDeleteId === category.id ? <div className="row-actions"><span>{t('Удалить раздел?')}</span><button className="danger-button" disabled={isSaving} type="button" onClick={() => removeCategory(category.id)}>{t('Да, удалить')}</button><button className="secondary-button" disabled={isSaving} type="button" onClick={() => setCategoryDeleteId(null)}>{t('Отмена')}</button></div> : <div className="row-actions">{canUpdate && <button className="secondary-button" disabled={isSaving} type="button" onClick={() => { clearError(); setCategoryForm({ ...category }) }}>{t('Изменить')}</button>}{canDelete && <button className="danger-button" disabled={isSaving} type="button" onClick={() => { clearError(); setCategoryDeleteId(category.id) }}>{t('Удалить')}</button>}</div>}
                </div>
              ))}
            </div>
            {(categoryForm.id ? canUpdate : canCreate) && <form className="crud-form knowledge-form" onSubmit={submitCategory}><h3>{categoryForm.id ? t('Изменить раздел') : t('Новый раздел')}</h3><label><span>{t('Название')}</span><input disabled={isSaving} maxLength={120} required value={categoryForm.name} onChange={(event) => setCategoryForm({ ...categoryForm, name: event.target.value })} /></label><label><span>{t('Описание')}</span><textarea disabled={isSaving} maxLength={300} rows={2} value={categoryForm.description} onChange={(event) => setCategoryForm({ ...categoryForm, description: event.target.value })} /></label><div className="form-actions"><button disabled={isSaving} type="submit">{categoryForm.id ? t('Сохранить раздел') : t('Создать раздел')}</button>{categoryForm.id && <button className="secondary-button" disabled={isSaving} type="button" onClick={() => { clearError(); setCategoryForm(emptyKnowledgeCategoryForm) }}>{t('Отмена изменения')}</button>}</div></form>}
          </div>
        </Modal>
      )}

      {deleteTarget && (
        <Modal title={t('Удалить статью?')} onClose={() => { if (!isSaving) setDeleteTargetId(null) }}>
          {error && <p className="form-error" role="alert">{t(error)}</p>}
          <div className="confirm-modal-body"><p>{t('Статья будет удалена из базы знаний.')}</p><strong>{deleteTarget.title}</strong></div>
          <div className="form-actions"><button className="danger-button" disabled={isSaving} type="button" onClick={removeArticle}>{t('Удалить')}</button><button className="secondary-button" disabled={isSaving} type="button" onClick={() => setDeleteTargetId(null)}>{t('Отмена')}</button></div>
        </Modal>
      )}
    </DashboardShell>
  )
}
