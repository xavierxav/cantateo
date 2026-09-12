(function () {
  'use strict';

  const fieldSets = {
    dimanche: ['temps', 'semaine', 'jour', 'annee'],
    semaine: ['temps', 'semaine', 'jour', 'parite'],
    fete: ['nom_fete', 'annee'],
  };

  const allManagedFields = ['temps', 'semaine', 'jour', 'parite', 'annee', 'nom_fete'];

  function getStandaloneRow(fieldName) {
    const field = document.getElementById(`id_${fieldName}`);
    if (!field) {
      return null;
    }
    return field.closest('.form-row') || field.closest('.form-row > div') || field.parentElement;
  }

  function getInlineCell(typeField, fieldName) {
    const tableRow = typeField.closest('tr');
    if (tableRow) {
      return tableRow.querySelector(`.field-${fieldName}`);
    }

    const inlineBlock = typeField.closest('.inline-related');
    if (inlineBlock) {
      const field = inlineBlock.querySelector(`[id$="-${fieldName}"]`);
      if (field) {
        return field.closest('.form-row') || field.parentElement;
      }
    }
    return null;
  }

  function getManagedFieldContainer(typeField, fieldName) {
    if (typeField.id === 'id_type_moment') {
      return getStandaloneRow(fieldName);
    }
    return getInlineCell(typeField, fieldName);
  }

  function syncMomentFields(typeField) {
    const visibleFields = new Set(fieldSets[typeField.value] || fieldSets.dimanche);
    allManagedFields.forEach((fieldName) => {
      const container = getManagedFieldContainer(typeField, fieldName);
      if (container) {
        container.hidden = !visibleFields.has(fieldName);
      }
    });
  }

  function bindTypeField(typeField) {
    if (!typeField || typeField.dataset.momentTypeBound === 'true') {
      return;
    }
    typeField.dataset.momentTypeBound = 'true';
    typeField.addEventListener('change', () => syncMomentFields(typeField));
    syncMomentFields(typeField);
  }

  function bindMomentTypeFields(root) {
    root.querySelectorAll('#id_type_moment, [id$="-type_moment"]').forEach(bindTypeField);
  }

  document.addEventListener('DOMContentLoaded', () => {
    bindMomentTypeFields(document);
  });

  document.addEventListener('formset:added', (event) => {
    bindMomentTypeFields(event.target);
  });
}());
