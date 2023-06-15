import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import { showErrorMessage } from '@jupyterlab/apputils';
import { URLExt, PathExt } from '@jupyterlab/coreutils';
import { IFileBrowserFactory } from '@jupyterlab/filebrowser';
import { ServerConnection } from '@jupyterlab/services';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';
import { each } from '@lumino/algorithm';
import { unarchiveIcon } from './icon';

const EXTRACT_QZV_URL = 'extract-qzv';
const FILE_EXTENSION = '.qzv';


namespace CommandIDs {
  export const extractQzv = 'filebrowser:extract-qzv';
}

function extractArchiveRequest(path: string): Promise<string> {
  const settings = ServerConnection.makeSettings();

  const baseUrl = settings.baseUrl;
  let url = URLExt.join(baseUrl, EXTRACT_QZV_URL, URLExt.encodeParts(path));

  const fullurl = new URL(url);

  const xsrfTokenMatch = document.cookie.match('\\b_xsrf=([^;]*)\\b');
  if (xsrfTokenMatch) {
    fullurl.searchParams.append('_xsrf', xsrfTokenMatch[1]);
  }

  url = fullurl.toString();
  const request = { method: 'GET' };

  return ServerConnection.makeRequest(url, request, settings).then(response => {
    if (response.status !== 200) {
      response.json().then(data => {
        showErrorMessage('Fail to extract the archive file', data.reason);
        throw new ServerConnection.ResponseError(response);
      });
    }
    return response.json().then(bag => bag.data as string);
  });
}

/**
 * Initialization data for the jupyter-archive extension.
 */
const extension: JupyterFrontEndPlugin<void> = {
  id: '@hadim/jupyter-archive:archive',
  autoStart: true,
  requires: [IFileBrowserFactory],
  optional: [ITranslator],
  activate,
}


async function activate(
  app: JupyterFrontEnd,
  factory: IFileBrowserFactory,
  translator: ITranslator | null
) {
  const trans = (translator ?? nullTranslator).load('jupyter_archive');

  console.log('JupyterLab extension jupyter-archive is activated!');

  const { commands } = app;
  const { tracker } = factory;

  const allowedArchiveExtensions = [FILE_EXTENSION];

  // matches file filebrowser items
  const selectorNotDir = '.jp-DirListing-item[data-isdir="false"]';

  // Add the 'extractArchive' command to the file's menu.
  commands.addCommand(CommandIDs.extractQzv, {
    execute: () => {
      const widget = tracker.currentWidget;
      if (widget) {
        each(widget.selectedItems(), item => {
          const promise = extractArchiveRequest(item.path);
          promise.then(url => window.open(url, '_blank'));
        });
      }
    },
    icon: unarchiveIcon,
    isVisible: () => {
      const widget = tracker.currentWidget;
      let visible = false;
      if (widget) {
        const firstItem = widget.selectedItems().next();
        if (firstItem) {
          const basename = PathExt.basename(firstItem.path);
          const splitName = basename.split('.');
          let lastTwoParts = '';
          if (splitName.length >= 2) {
            lastTwoParts =
              '.' + splitName.splice(splitName.length - 2, 2).join('.');
          }
          visible =
            allowedArchiveExtensions.indexOf(PathExt.extname(basename)) >=
            0 || allowedArchiveExtensions.indexOf(lastTwoParts) >= 0;
        }
      }
      return visible;
    },
    label: trans.__('View QZV')
  });

  // Add to right-click context menu
  app.contextMenu.addItem({
    command: CommandIDs.extractQzv,
    selector: selectorNotDir,
    rank: 10
  });
}

export default extension;
